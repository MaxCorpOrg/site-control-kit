# Исполнитель приглашений Telegram

## Что Это
`Telegram Invite Executor` — новый безопасный execution-слой внутри `site-control-kit` для `Telegram Invite Manager`.

Он не делает массовое добавление пользователей в чат и не реализует обход лимитов Telegram.
Его задача другая:
- держать конфигурацию consent-based invite workflow;
- готовить execution-plan для оператора;
- использовать `site-control` для Telegram Web и Telegram Desktop portable actor для Desktop-assisted шагов;
- сохранять execution-артефакты;
- записывать результат ручных действий обратно в `invite_state.json`.

## Файлы
- `scripts/telegram_invite_executor.py`
- `scripts/telegram_invite_executor_gui.sh`
- `tests/test_telegram_invite_executor.py`

Видимый operator entrypoint по-прежнему живёт в `tools/telegram/invite_manager/`, а подключение в unified panel идёт через `tools/telegram/invite_manager/tool_manifest.json`, без переноса самого executor-кода в platform-layer.
Общий Telegram operator hub теперь живёт в `tools/telegram/`.

## Как он связан с менеджером приглашений
`Invite Manager` остаётся источником истины по пользователям и статусам:
- `invite_state.json`
- `invite_run.json`

`Invite Executor` использует тот же `invite_state.json`, но работает уже на слое исполнения:
- `configure`
- `plan`
- `ensure-portable`
- `prepare-next`
- `desktop-send-link`
- `desktop-open-add-members`
- `inspect-chat`
- `open-chat`
- `add-contact`
- `record`
- `report`

## Что хранится в состоянии
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
    },
    "portable_actor": {
      "profile_name": "AK",
      "profile_dir": "/home/max/TelegramPortableAK",
      "account_username": "@M_a_g_g_i_e",
      "account_label": "@M_a_g_g_i_e"
    }
  }
}
```

## Артефакты выполнения
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
  --portable-profile-name "AK" \
  --portable-profile-dir "/home/max/TelegramPortableAK" \
  --account-username "@M_a_g_g_i_e" \
  --requires-approval
```

`portable_actor` не заменяет browser-target. Это отдельная метка исполнителя для Telegram Desktop portable.
Для текущего рабочего сценария `Zhirotop_shop` actor должен указывать на аккаунт `@M_a_g_g_i_e`.

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

### `ensure-portable`
Проверяет, что настроенный Telegram Desktop portable actor существует и запущен.
Если передать `--launch-if-needed`, executor попробует поднять профиль через `telegram_portable.py launch`.

Пример для текущего actor:

```bash
cd /home/max/site-control-kit
python3 scripts/telegram_invite_executor.py ensure-portable \
  --job-dir "/home/max/telegram_invite_jobs/chat_Zhirotop_shop"
```

Ожидаемый результат:
- `portable_actor.profile_dir = /home/max/TelegramPortableAK`;
- `account_username = @M_a_g_g_i_e`;
- `running = true`;
- в `windows[]` видно окно Telegram Desktop с целевым чатом.

Перед Desktop-assisted invite-flow эта проверка обязательна: она защищает от ситуации, когда агент работает не тем аккаунтом.

### `prepare-next`
Один быстрый orchestration-шаг для Desktop portable flow.
Команда:
- проверяет `portable_actor`;
- при `--launch-if-needed` запускает portable-профиль, если он не открыт;
- выбирает одного consented пользователя из `checked`, а если таких нет — из `new`;
- если пользователь был `new`, переводит его в `checked` и пишет `invite_run.json`;
- создаёт `execution_plan.json`;
- по умолчанию резервирует пользователя в `invite_link_created`;
- если передан новый `--username`, добавляет его только при явном `--consent yes`.

Пример для текущего `@M_a_g_g_i_e -> Zhirotop_shop`:

```bash
cd /home/max/site-control-kit
python3 scripts/telegram_invite_executor.py prepare-next \
  --job-dir "/home/max/telegram_invite_jobs/chat_Zhirotop_shop" \
  --username "@USERNAME" \
  --consent yes \
  --launch-if-needed
```

Если username уже есть в `invite_state.json`, можно не передавать `--username`: команда возьмёт следующего кандидата из очереди.
Если очередь пуста, вернётся `status = no_candidates`.

### `desktop-send-link`
Открывает DM ровно одного consented пользователя в Telegram Desktop portable actor и готовит/отправляет invite link.

Ограничения:
- пользователь должен быть в `invite_state.json`;
- `consent` должен быть `true`;
- допустимый статус по умолчанию: `invite_link_created` или `checked`;
- текст должен быть ASCII, поэтому дефолтное сообщение — сама invite link;
- реальная отправка требует явного `--confirm-send`;
- статус `sent` пишется только при `--record-result` и успешном `--confirm-send`.

Dry-run, без отправки:

```bash
cd /home/max/site-control-kit
python3 scripts/telegram_invite_executor.py desktop-send-link \
  --job-dir "/home/max/telegram_invite_jobs/chat_Zhirotop_shop" \
  --username "@USERNAME" \
  --dry-run
```

Live one-user отправка через текущий `@M_a_g_g_i_e` portable actor:

```bash
python3 scripts/telegram_invite_executor.py desktop-send-link \
  --job-dir "/home/max/telegram_invite_jobs/chat_Zhirotop_shop" \
  --username "@USERNAME" \
  --confirm-send \
  --record-result
```

Что делает команда:
1. проверяет `portable_actor` через `telegram_portable.py status`;
2. открывает DM через `tg://resolve?domain=<username>`;
3. печатает invite link в окно Telegram Desktop portable;
4. нажимает Enter только при `--confirm-send`;
5. пишет `execution_record.json`.

### `desktop-open-add-members`
Portable-only no-API UI path поверх Telegram Desktop accessibility/X11 primitives.

Команда:
- проверяет `portable_actor`;
- читает `log-diagnose` и может остановиться на `PEER_FLOOD` / `FLOOD_WAIT`;
- открывает группу через `tg://resolve?domain=<handle>`;
- открывает `Info` через AT-SPI accessibility node;
- пытается открыть `Add members` тоже через accessibility layer;
- может напечатать username в правое search field, если оно реально появилось.

Это не Telegram API и не blind pixel-click.
Под капотом используются новые primitive-команды `telegram_portable.py`:
- `accessibility-dump`
- `accessibility-click`
- `accessibility-type-text`

Dry-run для текущего `@M_a_g_g_i_e -> Zhirotop_shop`:

```bash
python3 scripts/telegram_invite_executor.py desktop-open-add-members \
  --job-dir "/home/max/telegram_invite_jobs/chat_Zhirotop_shop" \
  --username "@USERNAME" \
  --no-type-search \
  --dry-run
```

Попробовать дойти до search field и напечатать username:

```bash
python3 scripts/telegram_invite_executor.py desktop-open-add-members \
  --job-dir "/home/max/telegram_invite_jobs/chat_Zhirotop_shop" \
  --username "@USERNAME" \
  --type-search
```

Важные ограничения текущего first-cut path:
- команда пока не подтверждает финальный `Add`;
- статус пользователя в `invite_state.json` не меняет;
- если right-side search field не найден правее `--min-search-x`, команда останавливается до ввода, чтобы не печатать username в левый глобальный поиск Telegram Desktop;
- при `PEER_FLOOD` / `FLOOD_WAIT` live path по умолчанию останавливается, пока явно не передан `--allow-alerts`.

### `desktop-add-contact-profile`
Portable-only no-API path для добавления одного username именно в личные контакты текущего Telegram Desktop portable-аккаунта.

Команда:
- проверяет `portable_actor`;
- открывает `tg://resolve?domain=<username>&profile`;
- идёт по UI-пути `Add to contacts -> Done`;
- берёт первый клик не из статического blind-point, а из live accessibility-match `ДОБАВИТЬ КОНТАКТ`;
- для submit старается вычислить `Готово` от геометрии самой модалки `Новый контакт`, а не только от fallback ratio;
- пишет `execution_record.json` и PNG-скриншоты до/после/verify;
- не требует Telegram API и не работает массово сама по себе: один запуск = один username.

Пробный запуск без изменений:

```bash
cd /home/max/site-control-kit
python3 scripts/telegram_invite_executor.py desktop-add-contact-profile \
  --job-dir "/home/max/telegram_invite_jobs/contact_add__AK__users" \
  --username "@alice_123" \
  --dry-run
```

Реальное добавление:

```bash
python3 scripts/telegram_invite_executor.py desktop-add-contact-profile \
  --job-dir "/home/max/telegram_invite_jobs/contact_add__AK__users" \
  --username "@alice_123" \
  --confirm-add \
  --launch-if-needed
```

После успешного клика команда сама state пользователя не меняет.
Если нужен batch-режим с обновлением state, использовать именно `desktop-add-contact-batch`.

### `desktop-add-contact-batch`
Новый batch-режим для панели и CLI-обвязок.
Его задача: взять `.csv/.json` список consented username, создать или продолжить локальную job-state, привязать выбранный portable actor и по очереди вызвать существующий `desktop-add-contact-profile` для каждого username.

Команда:
- принимает `--job-dir`;
- если `invite_state.json` ещё нет, берёт `--input` и создаёт локальный state;
- сохраняет `portable_actor` в execution config;
- обрабатывает очередь по статусам `new/checked/failed`;
- после успешного live add помечает пользователя как `contact_added` при verify-статусе `contact_added_verified`;
- если `Добавить контакт` уже не видно, а в профиле уже есть `Изменить контакт` / `Удалить контакт`, команда теперь возвращает `contact_already_present` и тоже помечает пользователя как `contact_added`, а не как ошибку;
- при ошибке помечает пользователя как `failed`;
- пишет batch summary в `executions/<execution_id>/batch_contact_add.json`.

Пример для оператора:

```bash
cd /home/max/site-control-kit
python3 scripts/telegram_invite_executor.py desktop-add-contact-batch \
  --job-dir "/home/max/telegram_invite_jobs/contact_add__AK__users" \
  --input "/tmp/users.import.csv" \
  --portable-profile-name "AK" \
  --portable-profile-dir "/home/max/TelegramPortableAK" \
  --account-username "@M_a_g_g_i_e" \
  --confirm-add \
  --launch-if-needed
```

Для dry-run достаточно добавить `--dry-run`.
Если `invite_state.json` уже создан, `--input` нужен только для первого запуска: дальше batch-команда продолжает именно этот job-state и не переинициализирует его молча.

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

Пробный запуск без изменений:

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

## Графическая обёртка
Есть базовый wrapper:

```bash
bash scripts/telegram_invite_executor_gui.sh
```

Теперь GUI покрывает основные operator actions:
- `configure`
- `plan`
- `ensure-portable`
- `prepare-next`
- `desktop-send dry`
- `desktop-send live`
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
3. если flow идёт через Telegram Desktop portable, сначала проверяет `ensure-portable`;
4. открывает нужный чат через `site-control` или работает в подтверждённом portable-окне;
5. оператор выполняет безопасный invite workflow, запускает `desktop-send-link` для одного пользователя или запускает `add-contact` на одного пользователя с auto-verification before/after;
6. результат записывается через `record`.

## Следующий Шаг
Следующий логичный шаг — не forced-add path, а:
- безопасный invite link / join request orchestration;
- более сильная проверка вступления за пределами текущего видимого member list, если нужный пользователь не попал в правую панель сразу;
- optional operator checklist для реального Telegram UI;
- затем живой smoke на поднятом browser bridge.

## Заметки по живым проверкам

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

### Живое добавление `@Kamaz_master1` → `Zhirotop_shop`

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

### Живое добавление `@olegoleg48` → `Zhirotop_shop`

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

### Безопасная быстрая проверка: `inspect-chat` после нормализации `t.me` → `web.telegram`

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
