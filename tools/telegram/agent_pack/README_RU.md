# Telegram Agent Pack

Этот пакет нужен не оператору, а следующему агенту.

Его задача:

- сократить число лишних уточнений;
- дать устойчивую входную точку для типовых Telegram-задач;
- зафиксировать defaults и решения, которые уже приняты по проекту;
- держать machine-readable state отдельно от больших handoff markdown.

## Что здесь считается источником правды

1. `/home/max/site-control-kit/AGENTS.md`
2. `/home/max/site-control-kit/docs/PROJECT_STATUS_RU.md`
3. `/home/max/site-control-kit/docs/TELEGRAM_SUPERTOOL_ROADMAP_RU.md`
4. `/home/max/site-control-kit/tools/telegram/NEXT_CHAT_AGENT_PROMPT_RU.md`
5. versioned repo defaults:
   - `/home/max/site-control-kit/tools/telegram/agent_pack/agent_state.template.json`
   - `/home/max/site-control-kit/tools/telegram/agent_pack/VERIFICATION_MATRIX_RU.md`
6. persistent runtime state:
   - `~/.site-control-kit/telegram/agent/agent_state.json`

## Что хранится в persistent agent state

- `current_priority`
- `active_risks`
- `default_decisions`
- `last_verified_artifacts`
- `next_recommended_step`

Этот JSON не заменяет human docs.
Он нужен как короткий machine-readable checkpoint для следующего агента.

## Как думать о роли agent-pack

Это не отдельный ИИ-сервис.

Здесь “агент в проекте” =:

- runbook;
- defaults;
- orchestration mindset;
- verification matrix;
- persistent checkpoint;
- понятный next-step without re-discovery from scratch.

## Что лежит рядом в этом пакете

- `README_RU.md` — зачем существует agent-pack;
- `PLAYBOOK_RU.md` — рабочие правила продолжения проекта;
- `VERIFICATION_MATRIX_RU.md` — матрица проверок по слоям;
- `agent_state.template.json` — versioned machine-readable defaults прямо в репозитории;
- `~/.site-control-kit/telegram/agent/agent_state.json` — живая persistent копия state этой машины.

## Базовые defaults

- current model: `runbook_plus_orchestration`
- platform strategy: `tiered`
- first large architecture stage after current GUI bugfix:
  - `workflow_engine_and_job_store`
- standalone session runner:
  - не копировать в `site-control-kit`
  - держать отдельным runtime через контракт

## Что делать первым перед любой новой работой

1. Прочитать `AGENTS.md`
2. Прочитать `docs/PROJECT_STATUS_RU.md`
3. Прочитать `tools/telegram/NEXT_CHAT_AGENT_PROMPT_RU.md`
4. Прочитать `docs/TELEGRAM_SUPERTOOL_ROADMAP_RU.md`
5. Прочитать `tools/telegram/agent_pack/agent_state.template.json`
6. Прочитать `~/.site-control-kit/telegram/agent/agent_state.json`

Если machine-readable state расходится с human docs, приоритет у human docs и свежих проверенных артефактов.
