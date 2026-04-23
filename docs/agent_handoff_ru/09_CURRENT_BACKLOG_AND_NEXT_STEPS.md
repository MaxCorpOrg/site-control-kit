# Current Backlog And Next Steps

## Следующий Приоритет P0
### Reload Runtime И Добор Username После Уже Починенного Fallback
Нужен следующий логический шаг:
- перезагрузить unpacked extension в текущем Chrome profile, чтобы heartbeat снова начал рекламировать `click_menu_text`;
- подтвердить живьём уже написанный delivery-aware path не через legacy fallback, а через новый runtime;
- после reload повторить `fast` и `deep` batch-runs и двигать общий набор usernames к цели `40+`.

## Почему Это Следующий Приоритет
Потому что live smoke уже доказал:
- pipeline рабочий;
- profiles рабочие;
- batch wrapper снова рабочий;
- store-lock bottleneck в хабе уже снят;
- helper fallback в `mention`-режиме уже приносит реальных людей на живом чате;
- теперь главный остаточный limit уже в старом runtime и в глубине одного конкретного batch-run, а не в базовой архитектуре.

## Предлагаемый План Для Следующего Инженерного Шага
1. Reload unpacked extension в текущем Chrome profile.
2. Проверить, что `/api/clients` теперь содержит `meta.capabilities.content_commands`, включая `click_menu_text`.
3. Повторить batch-run `CHAT_PROFILE=fast CHAT_DEEP_MODE=mention`.
4. Повторить batch-run `CHAT_PROFILE=deep CHAT_DEEP_MODE=mention` с большим runtime budget.
5. Сравнить:
   - `new_usernames`
   - `deep_updated_total`
   - `members_with_username`
   - содержимое `latest_full.txt` и `latest_safe.txt`
6. Если после reload `click_menu_text` всё ещё не даёт прироста, переходить к следующему источнику usernames внутри Telegram Web, а не тратить ещё один цикл на wrapper/hub слой.

## Следующий Приоритет P1
### Разрезать Монолитный Exporter
`export_telegram_members_non_pii.py` уже слишком большой.
Следующее архитектурное улучшение:
- вынести profile/deep selection;
- вынести history/state helpers;
- вынести output/reporting.
- отдельно вынести batch-compatible stats/history/discovery слой, чтобы shell wrappers не зависели от монолита.

## Следующий Приоритет P2
### Единый User-Facing Control Layer
Сейчас shell/GUI уже понимают profile presets.
Но дальше можно сделать ещё лучше:
- унифицировать user prompts;
- показывать summary по profile effect;
- добавлять run summary сразу в GUI после завершения.

## Что Делать Не Нужно В Первую Очередь
- переписывать весь hub;
- пытаться заменять всё Telegram API-клиентом;
- делать большой UI-рефактор поверх zenity;
- добавлять внешние зависимости без явной необходимости.

## Хороший Следующий Acceptance
Хороший следующий результат будет таким:
- новый live run после reload даёт больше, чем текущий baseline:
  - baseline run: `/home/max/telegram_contact_batches/chat_-1002465948544/runs/20260423T115545Z/run.json`
  - baseline:
    - `new_usernames = 3`
    - `unique_members = 6`
    - `deep_updated_total = 3`
- в heartbeat видны `content_commands`;
- `export.log` показывает либо живой `click_menu_text`, либо более быстрый bailout без старого stall-поведения;
- `latest_full.txt` / `latest_safe.txt` растут дальше к целевой планке `40+`.
