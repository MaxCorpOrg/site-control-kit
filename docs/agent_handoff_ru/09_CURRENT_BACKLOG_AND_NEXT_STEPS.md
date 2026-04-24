# Current Backlog And Next Steps

## Следующий Приоритет P0
### Добор Username Через Более Агрессивный Helper/Discovery Path
Статус на 2026-04-24:
- sticky-author click-path уже внедрён: правый клик попадает в нижнюю 34px иконку автора через `telegram_sticky_author`, live probe дал `source=point`, `context_clicked=true`;
- sticky-author mention сейчас упирается не в координаты, а в отсутствие `Mention` в Telegram menu (`menu_missing`), после чего exporter уже запускает sticky helper fallback;
- sticky helper fallback подтвердил новые peer-bound usernames: `@alxkat` и `@Mitiacaramba`;
- live wrapper smoke `/tmp/telegram_live_sticky_icon.md` подтвердил это в обычном exporter path: `18` members, `10` usernames, sticky peer `6964266260` дошёл до `menu_missing`;
- combined artifact уже превысил цель 50: `/tmp/telegram_combined_54_usernames.txt`, но это объединение peer-bound и chat-mentions источников;
- pre-deep history backfill уже сделан;
- stale explicit history override уже закрыт;
- parser false-positive из message text уже закрыт;
- helper stale cross-peer misbind уже закрыт;
- known peer больше не должен тратить helper/deep runtime, если username есть в `identity_history.json`;
- live smoke `/tmp/telegram_live_after_prefill.md` подтвердил `9` pre-deep restored usernames на чате `https://web.telegram.org/a/#-1002465948544`;
- live verify `/tmp/telegram_live_verify_2.md` на явном stale history path дал `20` members, `8` usernames и `output_usernames_cleared_total = 0`;
- новый unknown peer `8055002493` стал первым реальным deep-кандидатом, но не отдал username за `90s`;
- значит P0 остаётся helper/discovery throughput, но уже для реально неизвестных peer, а не для повторного обхода history-known людей.

Нужен следующий логический шаг:
- не тратить ещё цикл на старый generic `Mention` path как на основной;
- если sticky-author найден, работать с ним через правый клик по нижней иконке, а не через профиль или текст сообщения;
- не тратить deep на peer, уже восстановленные из history;
- усиливать discovery/scroll и helper-tab throughput, чтобы за тот же runtime проходить больше peer;
- отдельно держать границу: "combined 50+" уже есть, "50 peer-bound members from fresh helper/profile" ещё нет;
- только так двигать общий набор usernames к цели `40+`.
- текущий baseline после свежего live-verify уже заметно лучше прежнего:
  - fast run `20260423T173223Z` дал `27` visible members и `10` safe usernames;
  - `latest_full.*` и `latest_safe.*` уже promoted на этот run;
  - но deep всё ещё обработал только `2` peer за `120s`;
  - а новый verify `20260424_171947_chat_1002465948544_20.md` подтвердил, что correctness-слой уже стабилен и следующий шаг должен улучшать именно throughput helper/discovery, а не снова чинить history/latest layer.
- scheduler cap уже внедрён в код (`TELEGRAM_CHAT_DEEP_STEP_MAX_SEC`), поэтому следующий практический шаг теперь такой:
  - использовать уже подтверждённый capped scheduler как базу;
  - повторить live `fast`/`deep` run с фокусом на helper throughput;
  - сравнивать рост по `deep_attempted_total`, `deep_updated_total`, `chat_scroll_steps_done` и `members_with_username`.

Отдельный подшаг рядом с этим приоритетом:
- больше не нужен как P0:
  - promotion policy для `latest_safe.*` уже учитывает fresh peer-rename.
  - numeric `@username` артефакты уже отфильтрованы в exporter/history/safe-layer.
  - pre-deep history backfill уже внедрён и покрыт тестом.

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
- numeric false-positive username уже снят и не должен больше искажать safe/history outputs;
- значит главный остаточный limit уже в product-path Telegram и в throughput helper/discovery слоя.

## Предлагаемый План Для Следующего Инженерного Шага
1. Поднять throughput helper fallback:
   - уменьшить лишние waits вокруг helper tabs;
   - сильнее сокращать profile-open path внутри helper;
   - агрессивнее заполнять несколько peer за один visible-layer.
2. Усилить discovery:
   - проверить, дал ли новый deep-step cap больше scroll steps за тот же runtime;
   - раньше отбрасывать peer без практического шанса на новый username.
3. Отдельно проверить unknown peer path:
   - начинать с peer, которых нет в `identity_history.json`;
   - не считать успешным run, который снова прошёл только history-known людей.
4. Повторить batch-run `CHAT_PROFILE=deep`.
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
  - baseline run: `/home/max/telegram_contact_batches/chat_-1002465948544/runs/20260423T173223Z/run.json`
  - baseline:
    - `members_with_username = 10`
    - `deep_attempted_total = 2`
    - `deep_updated_total = 2`
- в `export.log` меньше пустых retry на menu-path и больше реально обработанных peer через helper/discovery;
- `latest_full.txt` / `latest_safe.txt` растут дальше к целевой планке `40+`;
- если run обновил username у уже известного peer, это изменение не теряется ни в `snapshot_safe`, ни в `identity_history`, ни в `latest_safe.*`;
- если в raw run всплывёт очередной numeric peer-id, он не доезжает до `latest_safe.*` и numbered batch.
