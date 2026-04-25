# One User Flow RU

Сценарий для проверки одного пользователя через `Telegram Invite Manager`.

## Переменные

Заменить:
- `@USERNAME` на реальный username пользователя с явным согласием.
- `https://t.me/+INVITE_LINK` на реальную invite-ссылку вашего чата.

```bash
CHAT_URL="https://web.telegram.org/k/#-2465948544"
JOB_DIR="/home/max/telegram_invite_jobs/chat_-2465948544"
USERNAME="@USERNAME"
INVITE_LINK="https://t.me/+INVITE_LINK"
```

## 1. Добавить Одного Пользователя

```bash
cd /home/max/site-control-kit/tools/telegram_invite_manager

./bin/telegram-invite-manager add-user \
  --job-dir "$JOB_DIR" \
  --chat-url "$CHAT_URL" \
  --username "$USERNAME" \
  --display-name "$USERNAME" \
  --note "one user invite" \
  --source manual \
  --consent yes
```

## 2. Перевести В `checked`

```bash
./bin/telegram-invite-manager run \
  --job-dir "$JOB_DIR" \
  --limit 1 \
  --to-status checked
```

## 3. Настроить Invite Link

```bash
./bin/telegram-invite-executor configure \
  --job-dir "$JOB_DIR" \
  --invite-link "$INVITE_LINK" \
  --url-pattern "web.telegram.org/k/#-2465948544" \
  --requires-approval
```

## 4. Создать План На Одного

```bash
./bin/telegram-invite-executor plan \
  --job-dir "$JOB_DIR" \
  --limit 1 \
  --reserve
```

После этого пользователь перейдёт в `invite_link_created`.
План будет лежать в:

```text
$JOB_DIR/executions/<timestamp>/execution_plan.json
```

## 5. Открыть Чат Через Site Control

Сначала dry-run:

```bash
./bin/telegram-invite-executor open-chat \
  --job-dir "$JOB_DIR" \
  --dry-run
```

Потом реальное открытие:

```bash
./bin/telegram-invite-executor open-chat \
  --job-dir "$JOB_DIR"
```

## 5A. Снять Текущий Счётчик Чата

Если чат уже открыт в известной вкладке Telegram Web, можно штатно снять видимый счётчик участников:

```bash
./bin/telegram-invite-executor inspect-chat \
  --job-dir "$JOB_DIR" \
  --tab-id "<TELEGRAM_TAB_ID>" \
  --skip-open
```

Команда вернёт:
- `page_url`;
- `member_count`;
- `member_count_text`;
- признак `add_members_visible`.

## 6. Записать Результат

Если ссылка отправлена:

```bash
./bin/telegram-invite-executor record \
  --job-dir "$JOB_DIR" \
  --username "$USERNAME" \
  --status sent \
  --reason manual_link_sent
```

Если пользователь подал заявку:

```bash
./bin/telegram-invite-executor record \
  --job-dir "$JOB_DIR" \
  --username "$USERNAME" \
  --status requested \
  --reason join_request_seen
```

Если пользователь вступил:

```bash
./bin/telegram-invite-executor record \
  --job-dir "$JOB_DIR" \
  --username "$USERNAME" \
  --status joined \
  --reason joined_confirmed
```

## 6A. Live Add Через `Add Members`

Этот путь использовать только для одного consented пользователя из `invite_state.json`.
Он нужен для проверки реального UI Telegram Web, а не для массового инвайтинга.

Сначала открыть нужный чат и убедиться, что видна правая панель с кнопкой `Add Members`.
Если известен tab id:

```bash
./bin/telegram-invite-executor add-contact \
  --job-dir "$JOB_DIR" \
  --username "$USERNAME" \
  --tab-id "<TELEGRAM_TAB_ID>" \
  --skip-open \
  --dry-run
```

Проверочный режим без финального внешнего действия:

```bash
./bin/telegram-invite-executor add-contact \
  --job-dir "$JOB_DIR" \
  --username "$USERNAME" \
  --tab-id "<TELEGRAM_TAB_ID>" \
  --skip-open
```

Реальный клик `ADD`:

```bash
./bin/telegram-invite-executor add-contact \
  --job-dir "$JOB_DIR" \
  --username "$USERNAME" \
  --tab-id "<TELEGRAM_TAB_ID>" \
  --skip-open \
  --confirm-add \
  --verify-membership \
  --verify-wait 10 \
  --record-result
```

Важно:
- без `--confirm-add` команда не нажимает финальную кнопку Telegram `Add`;
- `--verify-membership` привязывает before/after `inspect-chat` к этому же execution record;
- `--record-result` ставит `joined` только если before/after проверка подтвердила рост `member_count`, иначе ставит `requested`;
- вручную писать `joined` только если Telegram Web, список участников или другой отдельный сигнал действительно подтвердил вступление.

## Проверить Состояние

```bash
./bin/telegram-invite-manager status \
  --job-dir "$JOB_DIR"

./bin/telegram-invite-executor report \
  --job-dir "$JOB_DIR"
```

## Что Считать Успехом

- `invite_state.json` создан или обновлён.
- Пользователь прошёл `new -> checked -> invite_link_created`.
- Создан `execution_plan.json`.
- `open-chat` открыл или активировал нужный Telegram chat.
- После ручного действия статус записан через `record`.

## Последний Smoke

Дата: `2026-04-24`

Рабочий каталог:

```text
/home/max/telegram_invite_jobs/chat_-2465948544/
```

Тестовый пользователь:

```text
@sitectl_smoke_user
```

Результат:
- `add-user` сработал;
- `run --limit 1` сработал;
- `plan --limit 1 --reserve` сработал;
- `open-chat` реально открыл Telegram Web через bridge;
- открытая вкладка: `614280462`;
- после проверки тестовая запись помечена как `skipped`.

Главные артефакты:

```text
/home/max/telegram_invite_jobs/chat_-2465948544/executions/20260424T123754Z/execution_plan.json
/home/max/telegram_invite_jobs/chat_-2465948544/executions/20260424T123800Z/execution_record.json
```

## Live Test: `@Kamaz_master1`

Дата: `2026-04-24`

Цель:

```text
https://t.me/Zhirotop_shop
```

Job:

```text
/home/max/telegram_invite_jobs/chat_Zhirotop_shop/
```

Команды прошли:
- `add-user`
- `run --limit 1 --to-status checked`
- `configure --invite-link https://t.me/Zhirotop_shop`
- `plan --limit 1 --reserve`
- `open-chat`

Результат на `2026-04-24`:
- `@Kamaz_master1` находился в статусе `invite_link_created`;
- открыт Telegram Web tab `614280505`;
- URL вкладки: `https://web.telegram.org/k/#@Zhirotop_shop`;
- фактическая отправка сообщения пользователю не выполнялась.

Артефакты:

```text
/home/max/telegram_invite_jobs/chat_Zhirotop_shop/invite_state.json
/home/max/telegram_invite_jobs/chat_Zhirotop_shop/runs/20260424T142342Z/invite_run.json
/home/max/telegram_invite_jobs/chat_Zhirotop_shop/executions/20260424T142347Z/execution_plan.json
/tmp/tg_invite_zhiritop_page_url.json
/tmp/tg_invite_zhiritop_body_text.json
/tmp/tg_invite_zhiritop_report.json
```

Чтобы зафиксировать реальную отправку после ручного действия:

```bash
cd /home/max/site-control-kit/tools/telegram_invite_manager

./bin/telegram-invite-executor record \
  --job-dir "/home/max/telegram_invite_jobs/chat_Zhirotop_shop" \
  --username "@Kamaz_master1" \
  --status sent \
  --reason manual_link_sent
```

## Live Add Test: `@Kamaz_master1`

Дата: `2026-04-25`

Живой тест был продолжен через Telegram Web tab:

```text
614280764
```

Ручной проверенный UI-path:
- открыть `https://web.telegram.org/k/#@Zhirotop_shop`;
- нажать `#column-right .profile-container.can-add-members button.btn-circle.btn-corner`;
- дождаться `.add-members-container .selector-search-input`;
- ввести `Kamaz_master1`;
- выбрать строку `.add-members-container .chatlist a.row[data-peer-id="1404471788"]`;
- нажать `.add-members-container > .sidebar-content > button.btn-circle.btn-corner`;
- подтвердить `.popup-add-members .popup-buttons button:nth-child(1)`.

Факт:
- popup подтверждения закрылся;
- явной ошибки Telegram не показал;
- сервисного сообщения `joined/added` не найдено;
- счётчик остался `2 440 members`;
- статус записан как `requested`.

Артефакт:

```text
/home/max/telegram_invite_jobs/chat_Zhirotop_shop/executions/20260425T052501Z/execution_record.json
```

## Live Add Test: `@olegoleg48`

Дата: `2026-04-25`

Пользователь был добавлен в тот же job:

```text
/home/max/telegram_invite_jobs/chat_Zhirotop_shop/
```

Проверка перед live add:
- `inspect-chat` показал `2 440 members`.

Live add:
- `add-user` создал запись `@olegoleg48`;
- `mark --status checked` перевёл её в `checked`;
- `add-contact --confirm-add --record-result` нашёл пользователя как `Oleg S`, `data-peer-id="1410391920"`;
- финальная кнопка `Add` была нажата;
- статус в state записан как `requested`.

Проверка после live add:
- повторный `inspect-chat` сразу после действия показал `2 440 members`;
- повторная проверка через ожидание тоже показала `2 440 members`;
- явных ошибок `privacy/cannot/too many/error` не было.

Вывод:
- UI-path до реального `Add` работает;
- рост счётчика участников не подтверждён;
- для таких кейсов не писать `joined`, пока Telegram не даст отдельного подтверждения.

Артефакт:

```text
/home/max/telegram_invite_jobs/chat_Zhirotop_shop/executions/20260425T061336Z/execution_record.json
```
