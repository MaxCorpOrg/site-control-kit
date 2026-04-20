# Known Issues And Live Findings

## Самый Важный Актуальный Live-Факт
Главный текущий bottleneck — не stale runtime и не отсутствие `Mention` как такового.
Главный bottleneck сейчас:
- `click_menu_text` в некоторых deep-шагах получает `expired no delivery`;
- после этого exporter тратит ещё несколько menu-attempts на тот же peer;
- только потом уходит в URL fallback.

Именно это сейчас съедает runtime.

## Что Уже Не Является Главной Проблемой
### Stale runtime
Снят.
Self-reload и capability handshake уже работают.

### Forced tab targeting
Свежий regression починен.
`CHAT_TAB_ID` без `CHAT_CLIENT_ID` теперь снова рабочий.

### Полный провал mention-path
Снят.
Есть live-подтверждённые run, где mention/deep без history backfill реально собирает новые usernames.

## Что Подтверждено Живьём
### Fast vs Deep
На одной и той же history/discovery базе:
- `fast` дал меньше новых deep usernames, но больше опирался на backfill;
- `deep` дал больше новых реальных `@username`, но дороже по runtime.

### URL fallback живой
Есть реальные run, где `Mention` не кликается, но URL fallback всё равно вытаскивает username.

### Group dialog restore в целом работает лучше, чем раньше
Раньше один тяжёлый peer мог ломать остаток deep-step.
Теперь path заметно устойчивее, хотя warning-поведение всё ещё встречается.

## Основные Открытые Риски
1. `expired no delivery` внутри deep menu path.
2. Лишние menu retries после delivery failure.
3. Неидеальный возврат в целевой dialog в некоторых длинных цепочках.
4. Монолитность `export_telegram_members_non_pii.py`.

## Самый Полезный Мысленный Фильтр Для Следующего Агента
Если следующий баг снова звучит как "не собрал username", не надо начинать с нуля.
Нужно проверить:
- был ли deep вообще запущен;
- был ли `click_menu_text`;
- был ли `expired no delivery`;
- был ли URL fallback;
- не спас ли результат history backfill;
- что именно вычистил safe layer.
