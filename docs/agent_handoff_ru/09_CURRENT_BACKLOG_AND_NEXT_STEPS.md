# Current Backlog And Next Steps

## Следующий Приоритет P0
### Delivery-Aware Bailout Для Deep Menu Path
Нужен следующий логический шаг:
- если `click_menu_text` получает `expired no delivery`, не жечь ещё несколько одинаковых попыток;
- раньше уходить в URL fallback;
- сохранить устойчивость recovery.

## Почему Это Следующий Приоритет
Потому что live smoke уже доказал:
- pipeline рабочий;
- profiles рабочие;
- deep реально приносит новых людей;
- главный runtime leak сидит именно в delivery-flaky menu path.

## Предлагаемый План Для Следующего Инженерного Шага
1. Локализовать, где именно учитывается outcome `click_menu_text`.
2. Ввести отдельную ветку для delivery-failure outcome.
3. Раньше завершать menu retries для такого peer.
4. Переходить в URL fallback после первого или максимум второго delivery-failure window.
5. Добавить тесты на эту ветку.
6. Повторить live comparison `fast` vs `deep`.

## Отдельный Трек: Invite Manager

Новый `Telegram Invite Manager` уже существует как manager/state слой.
Поверх него теперь есть и `Telegram Invite Executor` как execution-слой.
Что уже подтверждено в этом треке:
1. `add-contact` умеет привязывать before/after `inspect-chat` к одному live add;
2. `joined` теперь ставится только по сильному сигналу:
   - выбранный `peer_id` появился в видимом member list;
   - или вырос `member_count`;
3. public `https://t.me/<handle>` без явного browser-target теперь открывается как `https://web.telegram.org/k/#@<handle>`.

Следующий шаг для этого трека:
1. не добавлять опасный массовый path;
2. вынести подтверждение вступления за пределы текущего видимого member list, если нужный peer не попадает в правую панель сразу;
3. добить безопасный orchestration через invite links или join requests;
4. после выбора реального consented username прогнать one-user flow уже не на `/tmp`, а на рабочем `~/telegram_invite_jobs/...`;
5. сохранить тот же уровень артефактов и state discipline, что уже есть у export pipeline.

## Следующий Приоритет P1
### Разрезать Монолитный Exporter
`export_telegram_members_non_pii.py` уже слишком большой.
Следующее архитектурное улучшение:
- вынести profile/deep selection;
- вынести history/state helpers;
- вынести output/reporting.

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
- новый live run с `deep` даёт не меньше `deep_updated_total`, чем сейчас;
- число бесполезных menu retries уменьшается;
- в логах меньше повторов после `expired no delivery`.
