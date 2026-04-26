# Agent Start Here

Этот файл обязателен для любого агента, который заходит в `/home/max/site-control-kit`.
Перед любыми командами, правками, live-run или git-действиями сначала читать этот файл, потом `CODEX_STATE.md`, потом `docs/agent_handoff_ru/00_START_HERE.md`.

## Куда Смотреть Сразу
1. `AGENT_START_HERE.md`
2. `CODEX_STATE.md`
3. `docs/agent_handoff_ru/00_START_HERE.md`
4. `docs/PROJECT_STATUS_RU.md`
5. `docs/agent_handoff_ru/08_KNOWN_ISSUES_AND_LIVE_FINDINGS.md`
6. `docs/agent_handoff_ru/09_CURRENT_BACKLOG_AND_NEXT_STEPS.md`

## Что Это За Ветка
- Репозиторий: `site-control-kit`
- Ветка: `main`
- Активная тема: Telegram export path
- Цель не менялась: собирать именно peer-bound Telegram `@username` и двигаться к `100`

## Где Мы Закончили Работу
- Базовый ранний blocker в hub control-plane уже снят.
- Повторный helper tab/session churn уже снят.
- Пустой `RightColumn` shell больше не главный blocker.
- Последний точный blocker:
  - live Telegram DOM нестабильно materialize-ит target helper-route;
  - `_soft_confirm_helper_target_route()` уже добавлен и иногда даёт пройти дальше identity gate;
  - но в большинстве свежих live-run helper peer всё ещё завершается на `helper-soft-route matched=0` / `helper-wait-identity matched=0`.

## Последние Важные Артефакты
- Лучший live ceiling по username пока здесь:
  - `/tmp/tg_mention_probe_live/chat_-1002465948544/runs/20260426T060315Z/run.json`
- Первый isolated run, где helper реально прошёл дальше identity gate:
  - `/tmp/tg_mention_probe_live_softroute/chat_-1002465948544/runs/20260426T081833Z/run.json`
  - `/tmp/tg_mention_probe_live_softroute/chat_-1002465948544/runs/20260426T081833Z/export.log`
  - `/tmp/tg_mention_probe_live_softroute/chat_-1002465948544/runs/20260426T081833Z/export_stats.json`
- Два свежих run, которые подтвердили текущий blocker:
  - `/tmp/tg_mention_probe_live_softroute2/chat_-1002465948544/runs/20260426T082107Z/run.json`
  - `/tmp/tg_mention_probe_live_softroute3/chat_-1002465948544/runs/20260426T082310Z/run.json`

## Что Именно Менялось В Последнем Цикле
- `scripts/export_telegram_members_non_pii.py`
  - добавлен `_soft_confirm_helper_target_route()`
  - helper-route soft-confirm защищён от conflicting header/title
  - после `soft=1` helper делает только короткий foreground kick
  - numeric helper-route больше не жжёт budget на пустой `quick-url/page-url`
- `tests/test_telegram_export_runtime.py`
  - добавлены регрессии под soft-route accept/reject и soft-route helper-read path
- `CODEX_STATE.md`
  - зафиксированы последние live runs, текущий blocker и точный следующий шаг
- `docs/PROJECT_STATUS_RU.md`
  - добавлен свежий статус по soft-route fallback
- `docs/CHANGES_RU.md`
  - добавлена запись о helper soft-route fallback
- `docs/agent_handoff_ru/00_START_HERE.md`
  - обновлена точка входа новым hot-fact
- `docs/agent_handoff_ru/08_KNOWN_ISSUES_AND_LIVE_FINDINGS.md`
  - добавлены свежие live-факты и точный residual blocker
- `docs/agent_handoff_ru/09_CURRENT_BACKLOG_AND_NEXT_STEPS.md`
  - зафиксирован следующий узкий инженерный шаг

## С Чего Начинать Следующему Агенту
1. Прочитать этот файл.
2. Прочитать `CODEX_STATE.md`.
3. Проверить `git status --short --branch`.
4. Не делать `git reset` / `git checkout` в грязном дереве без прямого запроса.
5. Если работа продолжается по Telegram export, держаться только этого path.
6. Если меняется поведение, синхронно обновлять:
   - `CODEX_STATE.md`
   - `docs/PROJECT_STATUS_RU.md`
   - `docs/CHANGES_RU.md`
   - `docs/agent_handoff_ru/00_START_HERE.md`
   - `docs/agent_handoff_ru/08_KNOWN_ISSUES_AND_LIVE_FINDINGS.md`
   - `docs/agent_handoff_ru/09_CURRENT_BACKLOG_AND_NEXT_STEPS.md`

## Следующий Узкий Шаг
- Не чинить снова shell/session/open-tab.
- Не тратить цикл на старый `helper-page-url` waste.
- Диагностировать source-of-truth для helper-route сразу после `navigate` / `activate`:
  - `get_page_url`
  - stale `tab_url`
  - tab title
  - helper header identity
- Цель следующего шага: найти безопасный стабильный сигнал, который позволит дойти до `.MiddleHeader .ChatInfo` profile-read без cross-peer misbind.
