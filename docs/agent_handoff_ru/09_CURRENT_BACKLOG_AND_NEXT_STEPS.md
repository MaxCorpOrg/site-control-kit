# Current Backlog And Next Steps

## Следующий Приоритет P0
### Добор Username Через Более Агрессивный Helper/Discovery Path
Нужен следующий логический шаг:
- не тратить ещё цикл на старый `Mention` path как на основной;
- усиливать discovery/scroll и helper-tab throughput, чтобы за тот же runtime проходить больше peer;
- только так двигать общий набор usernames к цели `40+`.
- текущий baseline после helper-only switch уже лучше прежнего:
  - fast run `20260423T141227Z` обрабатывает `4` peer за `120s`;
  - значит следующий шаг должен улучшать именно этот throughput, а не снова чинить history/latest layer.

Отдельный подшаг рядом с этим приоритетом:
- больше не нужен как P0:
  - promotion policy для `latest_safe.*` уже учитывает fresh peer-rename.

## Почему Это Следующий Приоритет
Потому что live smoke уже доказал:
- pipeline рабочий;
- profiles рабочие;
- batch wrapper снова рабочий;
- store-lock bottleneck в хабе уже снят;
- runtime reload уже рабочий, heartbeat рекламирует `click_menu_text`;
- wrapper уже сам открывает Telegram tab через bridge client;
- helper fallback в `mention`-режиме уже приносит реальных людей на живом чате;
- live body snapshot подтвердил, что текущий `MessageContextMenu` не содержит `Mention`;
- значит главный остаточный limit уже в product-path Telegram и в throughput helper/discovery слоя.

## Предлагаемый План Для Следующего Инженерного Шага
1. Поднять throughput helper fallback:
   - уменьшить лишние waits вокруг helper tabs;
   - сильнее сокращать profile-open path внутри helper;
   - агрессивнее заполнять несколько peer за один visible-layer.
2. Усилить discovery:
   - проходить больше scroll steps за тот же runtime;
   - раньше отбрасывать peer без практического шанса на новый username.
3. Повторить batch-run `CHAT_PROFILE=deep`.
5. Сравнить:
   - `new_usernames`
   - `deep_updated_total`
   - `members_with_username`
   - содержимое `latest_full.txt` и `latest_safe.txt`
6. Если helper/discovery optimisation всё ещё не даёт роста, искать следующий источник usernames внутри Telegram Web, а не тратить ещё один цикл на obsolete `Mention` path.

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
- новый live run после mention-open фикса даёт больше, чем текущий baseline:
  - baseline run: `/home/max/telegram_contact_batches/chat_-1002465948544/runs/20260423T141227Z/run.json`
  - baseline:
    - `members_with_username = 7`
    - `deep_attempted_total = 4`
    - `deep_updated_total = 1`
- в `export.log` меньше пустых retry на menu-path и больше реально обработанных peer через helper/discovery;
- `latest_full.txt` / `latest_safe.txt` растут дальше к целевой планке `40+`;
- если run обновил username у уже известного peer, это изменение не теряется ни в `snapshot_safe`, ни в `identity_history`, ни в `latest_safe.*`.
