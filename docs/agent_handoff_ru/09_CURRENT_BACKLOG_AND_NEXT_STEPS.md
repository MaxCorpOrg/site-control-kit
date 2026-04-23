# Current Backlog And Next Steps

## Следующий Приоритет P0
### Добор Username Через Починку Telegram Mention-Open Path
Нужен следующий логический шаг:
- локализовать, почему `context_click`/anchor path не открывает mention menu для части peer;
- усилить selectors/anchor strategy до открытия context menu на большем числе сообщений;
- только после этого снова гнать `deep` и двигать общий набор usernames к цели `40+`.

## Почему Это Следующий Приоритет
Потому что live smoke уже доказал:
- pipeline рабочий;
- profiles рабочие;
- batch wrapper снова рабочий;
- store-lock bottleneck в хабе уже снят;
- runtime reload уже рабочий, heartbeat рекламирует `click_menu_text`;
- wrapper уже сам открывает Telegram tab через bridge client;
- helper fallback в `mention`-режиме уже приносит реальных людей на живом чате;
- теперь главный остаточный limit уже в самом Telegram UI-path, а не в базовой архитектуре.

## Предлагаемый План Для Следующего Инженерного Шага
1. На живом DOM проверить текущие anchor/selectors для peer-avatar / peer-title, которые используются перед `context_click`.
2. Если selectors слишком узкие, расширить их или добавить alternate anchor path.
3. Если menu реально открывается, но плохо детектится, усилить post-context detection до `click_menu_text`.
4. Повторить batch-run `CHAT_PROFILE=deep CHAT_DEEP_MODE=mention`.
5. Сравнить:
   - `new_usernames`
   - `deep_updated_total`
   - `members_with_username`
   - содержимое `latest_full.txt` и `latest_safe.txt`
6. Если даже после усиления selectors прироста нет, переходить к следующему источнику usernames внутри Telegram Web, а не тратить ещё один цикл на wrapper/hub слой.

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
  - baseline run: `/home/max/telegram_contact_batches/chat_-1002465948544/runs/20260423T122059Z/run.json`
  - baseline:
    - `new_usernames = 4`
    - `members_with_username = 9`
    - `deep_updated_total = 9`
- в `export.log` меньше `mention context menu not opened` и больше прямых mention-open/click-path срабатываний;
- `latest_full.txt` / `latest_safe.txt` растут дальше к целевой планке `40+`.
