# Перечень изменений (русская версия)

Дата фиксации состояния: **24 апреля 2026**.

Этот документ описывает, что именно реализовано в `site-control-kit`, какие проблемы закрыты и где находятся ключевые файлы.

## 0. Актуализация состояния на 24 апреля 2026

### 0.0 Telegram sticky-author path
- После фикса попадания по sticky icon добавлен sticky helper fallback:
  - если `telegram_sticky_author context_click=true` открыл menu, но `Mention` отсутствует, exporter пробует helper-tab для того же sticky `peer_id`;
  - stats получили `sticky_helper_attempted` и `sticky_helper_updated`;
  - best-effort command missing-result grace сокращён до 0.4..1.2s, чтобы helper не зависал на selector miss до 90s.
- Live-подтверждение:
  - `/tmp/telegram_live_sticky_helper.md`: `306536305 -> @alxkat`
  - `/tmp/telegram_live_sticky_helper_fastgrace.md`: `1127139638 -> @Mitiacaramba`
- Combined deliverable:
  - `/tmp/telegram_combined_54_usernames.txt`
  - `/tmp/telegram_combined_54_usernames.json`
  - `/home/max/site-control-kit/artifacts/telegram_exports/20260424_164916_combined-usernames_1002465948544_54.txt`
  - `/home/max/site-control-kit/artifacts/telegram_exports/20260424_164916_combined-usernames_1002465948544_54.json`
  - count: `54` уникальных `@username` из текущих member/chat-mentions/batch источников.
- `extension/content.js` получил команду `telegram_sticky_author`.
- Команда ищет нижнюю прилипшую иконку автора Telegram Web через `elementsFromPoint`.
- Для `context_click=true` используется только большая avatar под нижней point-пробой; fallback на текст сообщения/reply-avatar для правого клика запрещён.
- `scripts/export_telegram_members_non_pii.py` сначала пробует sticky-author mention для текущего прилипшего автора и ограничивает deep этим peer, если sticky-author найден.
- Добавлены stats:
  - `sticky_authors_seen`
  - `sticky_mention_attempted`
  - `sticky_mention_updated`
- Live probe на текущем чате после extension `0.1.5`:
  - `peer_id=8055002493`
  - `source=point`
  - `point={x:512,y:539}`
  - `rect=506,535,540,569`, `34x34`
  - `context_clicked=true`
  - `Mention` в открытом Telegram menu не найден: `menu_missing`.
- Live wrapper smoke:
  - output: `/tmp/telegram_live_sticky_icon.md`
  - archive: `/home/max/site-control-kit/artifacts/telegram_exports/20260424_143524_chat_1002465948544_18.md`
  - результат: `18` members, `10` usernames
  - sticky path дошёл до menu-path, но Telegram вернул `menu_missing`.
- Проверено:
  - `node --check extension/content.js && node --check extension/background.js`
  - `python3 -m unittest discover -s tests -p 'test_*.py'` -> `117 tests OK`

### 0.0.1 Telegram history/parser/helper correctness
- `scripts/export_telegram_members_non_pii.py` теперь предпочитает более свежий archive `identity_history` перед устаревшим явным `CHAT_IDENTITY_HISTORY`, а из старого файла добирает только отсутствующие non-conflicting записи.
- `_parse_chat_members()` больше не может подхватить `@username` из текста сообщения: username ищется только в author/header block.
- Helper-tab больше не должен присваивать stale username от чужого профиля:
  - перед чтением username helper ждёт подтверждение ожидаемого `peer_id` или имени;
  - live ложный кейс `6964266260 (Evgeniy) -> @Tri87true` перестал воспроизводиться.
- Live verify:
  - `/tmp/telegram_live_verify.md` -> `14` members, `8` usernames;
  - `/tmp/telegram_live_verify_2.md` -> `20` members, `8` usernames;
  - archive: `/home/max/site-control-kit/artifacts/telegram_exports/20260424_171947_chat_1002465948544_20.md`
  - `output_usernames_cleared_total = 0`
- Chat-dir state подтверждённо обновлён:
  - `/home/max/telegram_contact_batches/chat_-1002465948544/identity_history.json`
  - `@super_pavlik -> 1621138520`
  - `@alxkat -> 306536305`
  - `@mitiacaramba -> 1127139638`

### 0.0.2 Telegram pre-deep history backfill
- `scripts/export_telegram_members_non_pii.py` теперь применяет history backfill до deep-обхода видимых участников чата.
- Это экономит helper/deep runtime: уже известные `peer_id` не попадают в `deep_targets`, если username можно восстановить из `identity_history.json`.
- Добавлены stats:
  - `history_prefilled`
  - `history_prefill_conflicts`
- Добавлен regression test: известный `peer_id` получает username из history, а `_enrich_usernames_deep_chat()` не вызывается.
- Проверено:
  - короткий runtime/helper набор: `27 tests OK`;
  - полный Telegram-related набор: `77 tests OK`.
- Live smoke:
  - чат: `https://web.telegram.org/a/#-1002465948544`
  - output: `/tmp/telegram_live_after_prefill.md`
  - archive: `/home/max/site-control-kit/artifacts/telegram_exports/20260424_132543_chat_1002465948544_22.md`
  - результат: `22` members, `9` usernames, `9` username восстановлены pre-deep из history.

## 0.1 Актуализация состояния на 23 апреля 2026

### 0.1.1 Telegram export зафиксирован живым run
Подтверждён рабочий end-to-end контур на:
- `/home/max/telegram_contact_batches/chat_-1002465948544/runs/20260423T173223Z/run.json`
- `/home/max/telegram_contact_batches/chat_-1002465948544/runs/20260423T173223Z/export.log`
- `/home/max/telegram_contact_batches/chat_-1002465948544/runs/20260423T173223Z/export_stats.json`

Факты:
- `unique_members = 27`
- `members_with_username = 10`
- `safe_count = 10`
- `new_usernames = 2`
- `latest_full.*` и `latest_safe.*` promoted на этот run

Новые numbered batch usernames:
- `@oleg_klsnkv`
- `@andreu_bogatchenko`

### 0.1.2 Telegram mention-path теперь честнее
- Если Telegram Web отвечает `No visible menu item found by text`, exporter больше не тратит шаг на пустые retry и сразу уходит в helper fallback.
- Это отражает текущее реальное состояние Telegram UI: `Mention` часто отсутствует в доступном context menu.

### 0.1.3 Numeric `@username` артефакты закрыты
- Ложные значения вида `@1291639730` больше не должны попадать в новые Telegram outputs.
- Фильтр добавлен и в exporter, и в history-loader, и в safe/batch helper.
- Active файлы `latest_safe.*`, `latest_full.*`, `identity_history.json` и numbered batches приведены к этому правилу.

## 1. Что создано с нуля

### 1.1 Локальный хаб управления (Python)
Реализован локальный HTTP-сервер, который принимает команды, раздаёт их клиентам-расширениям и сохраняет результаты.

Файлы:
- `webcontrol/server.py` — HTTP API (`/health`, `/api/clients/*`, `/api/commands/*`).
- `webcontrol/store.py` — in-memory + persistence (`state.json`), очередь команд, статусы.
- `webcontrol/config.py` — конфигурация хаба.
- `webcontrol/utils.py` — утилиты сериализации.

### 1.2 CLI для оператора
Реализован CLI для ручного и скриптового управления.

Файлы:
- `webcontrol/cli.py` — команды `serve`, `health`, `clients`, `state`, `send`, `wait`, `cancel`.
- `webcontrol/__main__.py` — запуск через `python3 -m webcontrol`.
- `pyproject.toml` — установка команды `sitectl`.

### 1.3 Расширение браузера (MV3)
Создано расширение-мост между реальными вкладками и локальным хабом.

Файлы:
- `extension/manifest.json` — разрешения и точки входа MV3.
- `extension/background.js` — heartbeat, polling, получение/выполнение команд, отправка результатов.
- `extension/content.js` — DOM-команды (`click`, `fill`, `wait_selector`, `extract_text`, `get_html`, `scroll`, `get_attribute`, `run_script`).
- `extension/options.*` — настройка URL хаба, токена и интервалов.
- `extension/popup.*` — диагностика клиента в 1 клик.

### 1.4 Скрипты эксплуатации
Файлы:
- `scripts/start_hub.sh` — запуск хаба с переменными окружения.
- `scripts/package_extension.sh` — упаковка расширения в zip.
- `scripts/export_feishu_bundle.py` — экспорт Feishu-страниц в Markdown (сырой + RU).

## 2. Что доработано для удобства

### 2.1 Быстрый локальный режим без ручной генерации токена
Добавлен единый токен по умолчанию:
- `local-bridge-quickstart-2026`

Поведение:
- Если `SITECTL_TOKEN` не задан, `start_hub.sh` запускает хаб в quickstart-режиме.
- CLI и расширение также имеют fallback на этот токен.
- Для production/сети рекомендуется обязательно переопределять токен.

### 2.2 Русификация пользовательской части расширения
Сделаны русские подписи в popup/options для более удобной эксплуатации:
- статус heartbeat/poll,
- кнопки диагностики,
- статусы сохранения настроек.

### 2.3 Документация для пользователя и ИИ
Подготовлен комплект русской документации по архитектуре, API, безопасности и сопровождению.

## 3. Протокол и команды

Поддерживаемые типы команд:
- `navigate`
- `click`
- `fill`
- `wait_selector`
- `extract_text`
- `get_html`
- `get_attribute`
- `scroll`
- `screenshot`
- `run_script`

Особенности:
- Команды ставятся в очередь и назначаются целевым клиентам (`client_id`).
- Каждый результат возвращается в хаб с финальным статусом (`completed/failed/canceled/expired`).
- История сохраняется в `~/.site-control-kit/state.json`.

## 4. Безопасность

Реализовано:
- проверка токена на всех `/api/*` endpoint;
- поддержка `X-Access-Token` и `Authorization: Bearer ...`;
- базовые рекомендации по изоляции хаба на `127.0.0.1`.

Ограничения:
- `run_script` может падать на сайтах со строгим CSP (запрет `unsafe-eval`). Это ожидаемое поведение браузера.

## 5. Тесты и примеры

Добавлено:
- `tests/test_store.py` — проверка ключевой логики очереди/статусов.
- `examples/*.json` — готовые примеры payload-команд.

## 6. Экспорт контента в Markdown

Подготовлен сценарий выгрузки контента страниц Feishu в локальные `.md`:
- сырой слой (raw),
- русский слой (RU),
- пакетный bundle-экспорт по ссылкам.

Это позволяет переносить знания сайта в локальную документационную базу.

## 7. Что важно при дальнейшем развитии

1. Не ломать API-контракт без миграции и обновления `docs/API.md`.
2. Не ослаблять auth-проверки токена.
3. При расширении типов команд сразу обновлять:
- `docs/API.md`,
- `docs/EXTENSION.md`,
- `examples/`.
4. Держать поведение deterministic для `state.json`.
