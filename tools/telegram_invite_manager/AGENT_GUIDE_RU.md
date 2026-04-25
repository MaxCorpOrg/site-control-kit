# Agent Guide RU: Telegram Invite Manager

Этот файл — короткая инструкция для агента, который продолжает работу с invite-инструментом.

## Сначала Прочитать

Из корня проекта:

```bash
cd /home/max/site-control-kit
```

Обязательно прочитать:
- `AGENTS.md`
- `docs/PROJECT_STATUS_RU.md`
- `docs/TELEGRAM_INVITE_MANAGER_RU.md`
- `docs/TELEGRAM_INVITE_EXECUTOR_RU.md`
- `tools/telegram_invite_manager/README.md`
- `tools/telegram_invite_manager/NEXT_CHAT_AGENT_PROMPT_RU.md`
- `tools/telegram_invite_manager/ONE_USER_FLOW_RU.md`

## Что Уже Сделано

Есть manager-слой:
- импорт CSV/JSON;
- `add-user` для одного пользователя;
- `invite_state.json`;
- `next/run/mark/report`;
- `runs/<timestamp>/invite_run.json`;
- GUI wrapper.

Есть execution-слой:
- `configure`;
- `plan`;
- `inspect-chat`;
- `open-chat`;
- `add-contact` для одного consented контакта через Telegram Web `Add Members`;
- `record`;
- `report`;
- `executions/<timestamp>/execution_plan.json`;
- `executions/<timestamp>/execution_record.json`;
- GUI wrapper.

Есть видимая папка инструмента:

```text
tools/telegram_invite_manager/
```

Есть отдельный copy-paste prompt для нового чата:

```text
tools/telegram_invite_manager/NEXT_CHAT_AGENT_PROMPT_RU.md
```

## Как Работать С Одним Пользователем

1. Добавить пользователя только при явном consent.
2. Перевести его в `checked`.
3. Настроить invite-link.
4. Создать execution-plan на `limit 1`.
5. Открыть чат через `site-control`.
6. Если нужен контроль по счётчику, снять его через `inspect-chat`.
7. Если нужен direct add через Telegram Web, использовать только `add-contact` на одного пользователя.
8. После ручного действия или live add записать результат через `record` либо `add-contact --record-result`.

Полная команда лежит в `ONE_USER_FLOW_RU.md`.

## Важные Статусы

- `new` — пользователь добавлен и ждёт проверки.
- `checked` — оператор подтвердил, что можно делать invite workflow.
- `invite_link_created` — создан или зарезервирован invite-plan.
- `sent` — ссылка/приглашение отправлены.
- `requested` — пользователь подал join request.
- `approved` — заявка одобрена.
- `joined` — пользователь вступил.
- `skipped` — не обрабатывать.
- `failed` — действие не удалось.

## Проверки После Правок

Всегда запускать:

```bash
cd /home/max/site-control-kit
PYTHONPATH="$PWD" python3 -m unittest discover -s tests -p 'test_*.py'
```

Если менялись Python-файлы:

```bash
python3 -m py_compile scripts/telegram_invite_manager.py scripts/telegram_invite_executor.py
```

Если менялись shell-файлы:

```bash
bash -n scripts/telegram_invite_manager_gui.sh scripts/telegram_invite_executor_gui.sh \
  tools/telegram_invite_manager/bin/telegram-invite-manager \
  tools/telegram_invite_manager/bin/telegram-invite-executor
```

## Что Нельзя Делать

- Не добавлять массовую автодобавлялку.
- Не делать multi-account обход лимитов.
- Не использовать список usernames без подтверждённого согласия.
- Не затирать state без бэкапа или явного запроса пользователя.
- Не ставить `joined`, если Telegram не дал проверяемого сигнала вступления. Для подтверждённого клика `ADD` без видимого `joined/added` использовать `requested`.

## Текущий Следующий Шаг

Живой one-user smoke в рабочем каталоге уже подтверждён:

```text
/home/max/telegram_invite_jobs/chat_-2465948544/
```

Факты smoke:
- `add-user` добавил `@sitectl_smoke_user`;
- `run --limit 1 --to-status checked` перевёл запись в `checked`;
- `plan --limit 1 --reserve` создал `execution_plan.json`;
- `open-chat` через `site-control` открыл Telegram tab `614280462`;
- после проверки запись помечена как `skipped` с reason `smoke_test_completed`.

Артефакты:
- `/tmp/tg_invite_real_add.json`
- `/tmp/tg_invite_real_run.json`
- `/tmp/tg_invite_real_configure.json`
- `/tmp/tg_invite_real_plan.json`
- `/tmp/tg_invite_real_open.json`
- `/tmp/tg_invite_real_record.json`
- `/home/max/telegram_invite_jobs/chat_-2465948544/executions/20260424T123754Z/execution_plan.json`
- `/home/max/telegram_invite_jobs/chat_-2465948544/executions/20260424T123800Z/execution_record.json`

Следующий практический шаг:
- заменить smoke username и placeholder invite-link на реальные значения;
- провести один consented user через тот же flow;
- после ручной отправки ссылки записать `sent`, `requested` или `joined`.

Для финального реального invite нужны:
- конкретный `@username` пользователя с consent;
- реальный invite-link нужного чата.

Без этих двух значений агент может проверять только manager/executor/open-chat, но не факт отправки приглашения.

## Live Test: `@Kamaz_master1` -> `Zhirotop_shop`

Дата: `2026-04-24`

Пользователь:

```text
@Kamaz_master1
```

Цель:

```text
https://t.me/Zhirotop_shop
```

Рабочий каталог:

```text
/home/max/telegram_invite_jobs/chat_Zhirotop_shop/
```

Что выполнено:
- создан отдельный job под `https://t.me/Zhirotop_shop`;
- `@Kamaz_master1` добавлен как consented one-user entry;
- запись прошла `new -> checked -> invite_link_created`;
- создан execution-plan на одного пользователя;
- через `site-control` открыт Telegram Web tab `614280505`;
- live page URL подтверждён как `https://web.telegram.org/k/#@Zhirotop_shop`;
- текст страницы подтверждает, что открыт чат `Жиротоп Shop`.

Артефакты:
- `/home/max/telegram_invite_jobs/chat_Zhirotop_shop/invite_state.json`
- `/home/max/telegram_invite_jobs/chat_Zhirotop_shop/runs/20260424T142342Z/invite_run.json`
- `/home/max/telegram_invite_jobs/chat_Zhirotop_shop/executions/20260424T142347Z/execution_plan.json`
- `/tmp/tg_invite_zhiritop_page_url.json`
- `/tmp/tg_invite_zhiritop_body_text.json`
- `/tmp/tg_invite_zhiritop_report.json`

Важно:
- на `2026-04-24` фактическая отправка сообщения пользователю не выполнялась;
- статус пользователя был `invite_link_created`;
- после ручной отправки ссылки нужно было вызвать `telegram-invite-executor record --status sent`.

## Live Add Test: `@Kamaz_master1` -> `Zhirotop_shop`

Дата: `2026-04-25`

Цель:

```text
@Kamaz_master1 -> https://t.me/Zhirotop_shop
```

Что проверено в Telegram Web через bridge:
- открыт tab `614280764`;
- URL подтверждён как `https://web.telegram.org/k/#@Zhirotop_shop`;
- в правой панели найден `Add Members`;
- поле поиска `.add-members-container .selector-search-input` принимает `Kamaz_master1`;
- Telegram вернул контакт `Камаз` с `data-peer-id="1404471788"`;
- строка выбрана, появился selected chip `Камаз`;
- Telegram показал popup `Are you sure you want to add Камаз ...`;
- финальная кнопка нажата через `.popup-add-members .popup-buttons button:nth-child(1)`;
- popup закрылся, видимых ошибок `privacy/cannot/too many/error` не было;
- сервисного `joined/added` в чате не появилось, счётчик остался `2 440 members`.

Финальная запись в state:

```bash
./tools/telegram_invite_manager/bin/telegram-invite-executor record \
  --job-dir /home/max/telegram_invite_jobs/chat_Zhirotop_shop \
  --username @Kamaz_master1 \
  --status requested \
  --reason live_add_members_confirmed_unverified_20260425
```

Артефакт записи:

```text
/home/max/telegram_invite_jobs/chat_Zhirotop_shop/executions/20260425T052501Z/execution_record.json
```

Вывод для следующего агента:
- live UI-path до финального `ADD` работает;
- итог Telegram Web неоднозначный, поэтому не писать `joined` без отдельной проверки в списке участников;
- для повторения использовать новую команду `telegram-invite-executor add-contact`, но только по одному consented пользователю.

## Live Add Test: `@olegoleg48` -> `Zhirotop_shop`

Дата: `2026-04-25`

Что проверено:
- до live add `inspect-chat` показал `2 440 members`;
- `@olegoleg48` добавлен в `invite_state.json` и переведён в `checked`;
- `add-contact --confirm-add --record-result` нашёл контакт как `Oleg S`, `data-peer-id="1410391920"`;
- popup подтверждения закрылся, видимой ошибки Telegram не было;
- после live add `inspect-chat` сразу и после ожидания показал те же `2 440 members`.

Финальная запись в state:

```text
@olegoleg48: checked -> requested
reason: live_add_members_confirmed_unverified
```

Артефакт:

```text
/home/max/telegram_invite_jobs/chat_Zhirotop_shop/executions/20260425T061336Z/execution_record.json
```

Практический вывод:
- кнопка `Add` реально нажимается;
- рост member count не подтверждён;
- `inspect-chat` теперь нужен как обязательная проверка до и после live add.
