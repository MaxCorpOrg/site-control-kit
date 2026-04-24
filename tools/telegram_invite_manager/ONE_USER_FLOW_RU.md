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

Результат:
- `@Kamaz_master1` находится в статусе `invite_link_created`;
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
