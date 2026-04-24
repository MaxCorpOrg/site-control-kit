# Agent Handoff RU: Start Here

Этот пакет нужен для любого нового агента, нового чата и нового этапа работы по `site-control-kit`.
Цель пакета: дать агенту один понятный вход, чтобы он мог быстро понять проект, текущее состояние и безопасно продолжить работу без повторного исследования с нуля.

## Для Кого Этот Пакет
- для ИИ-агентов, которые впервые заходят в репозиторий;
- для нового чата, где нет контекста прошлой работы;
- для handoff после большой серии Telegram/browser-изменений.

## Что Уже Есть В Репозитории
В проекте уже есть базовая документация:
- `AGENTS.md`
- `docs/PROJECT_WORKFLOW_RU.md`
- `docs/PROJECT_STATUS_RU.md`
- `docs/ARCHITECTURE.md`
- `docs/API.md`
- `docs/EXTENSION.md`
- `docs/AI_MAINTAINER_GUIDE.md`

Этот пакет не заменяет их полностью. Он собирает рабочую картину в одном месте, в правильном порядке чтения, и объясняет, как именно продолжать работу с текущего состояния.

## Обязательный Порядок Чтения
Читать в таком порядке:
1. `docs/agent_handoff_ru/00_START_HERE.md`
2. `docs/agent_handoff_ru/01_PROJECT_SCOPE_AND_GOALS.md`
3. `docs/agent_handoff_ru/02_ARCHITECTURE_MAP.md`
4. `docs/agent_handoff_ru/03_COMPONENTS_AND_ENTRYPOINTS.md`
5. `docs/agent_handoff_ru/04_TELEGRAM_EXPORT_PIPELINE.md`
6. `docs/agent_handoff_ru/05_STATE_AND_ARTIFACTS.md`
7. `docs/agent_handoff_ru/06_AGENT_WORKFLOW_AND_OPERATIONS.md`
8. `docs/agent_handoff_ru/07_TESTING_AND_ACCEPTANCE.md`
9. `docs/agent_handoff_ru/08_KNOWN_ISSUES_AND_LIVE_FINDINGS.md`
10. `docs/agent_handoff_ru/09_CURRENT_BACKLOG_AND_NEXT_STEPS.md`
11. `docs/agent_handoff_ru/10_HANDOFF_TEMPLATE_AND_COMMIT_POLICY.md`

После этого уже читать:
- `AGENTS.md`
- `docs/PROJECT_WORKFLOW_RU.md`
- `docs/PROJECT_STATUS_RU.md`
- при необходимости `docs/ARCHITECTURE.md`, `docs/API.md`, `docs/EXTENSION.md`

## Быстрый Старт Для Нового Агента
Перед любыми правками выполнить:

```bash
cd /home/max/site-control-kit
git status --short --branch
git log --oneline -n 15
PYTHONPATH="$PWD" python3 -m webcontrol clients
```

Если задача связана с Telegram, дальше посмотреть:

```bash
ls -la /home/max/telegram_contact_batches/chat_-1002465948544
find /home/max/telegram_contact_batches/chat_-1002465948544/runs -maxdepth 2 -name run.json | sort | tail
```

Текущий живой Telegram-чат: `https://web.telegram.org/a/#-1002465948544`.

## Что Агент Должен Понять После Чтения Пакета
- какую задачу реально решает проект;
- как устроен browser bridge;
- как именно работает Telegram pipeline;
- где лежат state files и run-артефакты;
- какие live-результаты уже подтверждены;
- какие проблемы ещё не закрыты;
- какой следующий технический приоритет уже очевиден.

## Что Сейчас Самое Важное
На текущем этапе проект уже не находится в состоянии "сырой прототип".
Основной рабочий контур живой:
- hub работает;
- extension работает;
- CLI работает;
- Telegram export работает;
- batch/safe/quarantine слои работают.

Главный текущий технический долг уже сместился в performance и resilience deep-path, а не в базовую функциональность.

## Текущий Telegram Sticky-Fact
Для Telegram username export следующий агент не должен снова искать координаты с нуля:
- текущий рабочий path: `telegram_sticky_author` с `context_click=true`;
- клик должен быть правой кнопкой по нижней прилипшей 34px иконке автора;
- не кликать по тексту сообщения, reply-avatar и не открывать профиль левой кнопкой;
- live probe на extension `0.1.5` подтвердил `source=point`, `point={x:512,y:539}`, `rect=506,535,540,569`, `context_clicked=true` для `peer_id=8055002493`;
- если после этого нет username, текущая причина обычно `menu_missing`: Telegram Web не показывает `Mention` в этом меню;
- после `menu_missing` exporter должен запускать sticky helper fallback для того же `peer_id`; live это уже дало `@alxkat` и `@Mitiacaramba`;
- explicit chat-dir `identity_history.json` больше не должен считаться источником истины, если archive state свежее: loader теперь предпочитает newer `updated_at` и только добирает missing non-conflicting записи;
- chat parser больше не имеет права брать `@username` из текста сообщения, только из author/header block;
- helper-tab теперь обязан подтвердить ожидаемый `peer_id` или имя перед чтением username, иначе возвращает `—`;
- свежий live verify с явным stale history path сохранил корректный `@super_pavlik -> 1621138520` и не воспроизвёл старый ложный helper-case `6964266260 -> @Tri87true`;
- combined output на 54 username уже лежит в `/tmp/telegram_combined_54_usernames.txt`, но это смешанный источник, не полностью peer-bound список.
