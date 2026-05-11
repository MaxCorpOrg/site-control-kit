# Checkpoint 2026-05-11

## Контекст

- Repo: `C:\site-control-kit-win-smoke`
- Branch: `main`
- Remote: `origin https://github.com/MaxCorpOrg/site-control-kit.git`
- Base commit before end-of-day commit:
  - `3c03277720714ff13745e659923019a3ac2f7a4d`
  - `Сохранил release checkpoint и handoff для следующего агента`

## Что сделано

- Завершён узкий Windows smoke вокруг `telegram-username-collector`, hub/runtime wrappers и browser wrappers.
- Подтверждён adopted-legacy runtime path через `%USERPROFILE%\.site-control-kit`.
- Синхронизированы handoff/state docs:
  - `AGENT_START_HERE.md`
  - `CODEX_STATE.md`
  - `docs/PROJECT_STATUS_RU.md`
  - `docs/agent_handoff_ru/00_START_HERE.md`
  - `docs/agent_handoff_ru/08_KNOWN_ISSUES_AND_LIVE_FINDINGS.md`
  - `docs/agent_handoff_ru/09_CURRENT_BACKLOG_AND_NEXT_STEPS.md`
- Обновлены project docs для следующего агента:
  - `README.md`
  - `docs/ARCHITECTURE.md`
  - `AGENTS.md`
  - `NEXT_STEPS.md`
  - `CHANGELOG.md`

## Изменённые файлы

### Код и тесты
- `pyproject.toml`
- `requirements.txt`
- `scripts/bootstrap_telegram_workstation.sh`
- `scripts/start_hub.ps1`
- `scripts/telegram_members_export_gui.py`
- `scripts/telegram_members_export_gui.sh`
- `scripts/telegram_gui/__init__.py`
- `scripts/telegram_gui/gtk_compat.py`
- `scripts/telegram_gui/app.py`
- `scripts/telegram_gui/services/portable_profiles.py`
- `scripts/telegram_gui/services/secrets.py`
- `scripts/telegram_gui/ui/panels.py`
- `scripts/telegram_gui/ui/styles.py`
- `scripts/telegram_gui/ui/window.py`
- `telegram-username-collector.cmd`
- `bash.cmd`
- `webcontrol/cli.py`
- `webcontrol/settings.py`
- `tests/test_settings.py`
- `tests/test_telegram_gui_backend_features.py`
- `tests/test_telegram_gui_portable_profiles.py`
- `tests/test_telegram_gui_process_runner.py`
- `tests/test_telegram_members_export_gui.py`

### Документация и handoff
- `README.md`
- `BROWSER_QUICKSTART.md`
- `AGENTS.md`
- `AGENT_START_HERE.md`
- `CODEX_STATE.md`
- `docs/ARCHITECTURE.md`
- `docs/INSTALL_OTHER_DEVICES_RU.md`
- `docs/PROJECT_STATUS_RU.md`
- `docs/agent_handoff_ru/00_START_HERE.md`
- `docs/agent_handoff_ru/08_KNOWN_ISSUES_AND_LIVE_FINDINGS.md`
- `docs/agent_handoff_ru/09_CURRENT_BACKLOG_AND_NEXT_STEPS.md`
- `NEXT_STEPS.md`
- `CHANGELOG.md`

## Проверки и команды

### Git и safety
- `git status --short --branch`
- `git branch --show-current`
- `git remote -v`
- `git diff --stat`
- `git diff --check`
- `git status --ignored --short`
- проверено, что `.env` отсутствует
- проверено, что `node_modules/` отсутствует
- проверено, что `.site-control-kit/`, `var/` и `*.log` остаются вне индекса
- проверено, что реальный runtime token не попал в tracked text files

### Windows smoke
- `scripts\start_hub.cmd`
- `.\browser.cmd status`
- `.\browser.cmd tabs`
- `python -m webcontrol --help`
- `python -m webcontrol browser --help`
- `python -m webcontrol runtime-env --format json --no-create`
- `.\telegram-username-collector.cmd`

### Unit tests
- `python -m unittest discover -s tests -p "test_*.py"`

## Ошибки и ограничения

- На текущей машине `docs/WINDOWS_SMOKE_HANDOFF_RU.md` отсутствует, поэтому smoke шёл по зафиксированному exact checklist из handoff и пользовательского задания.
- Effective runtime на этой машине — `legacy-adopted`, поэтому repo-local `var/site-control-kit` не создаётся и это не считается blocker-ом.
- Главный remaining risk сейчас операционный:
  - adopted Edge debug profile может снова потерять active unpacked-extension load state.
- Во время финального end-of-day verify client один раз стал stale/offline:
  - recovery снова был только runtime-side, без repo-правок;
  - помог повторный запуск Edge debug profile с `--disable-extensions-except=<repo>\extension` и `--load-extension=<repo>\extension`;
  - после этого `browser.cmd status` и `browser.cmd tabs` снова показали online client.
- `telegram-username-collector` на Windows не является GUI launcher:
  - ожидаемое поведение — controlled fast-fail без traceback и без GTK окна.

## Что важно не утащить в commit

- `.env`
- `.site-control-kit/`
- `var/`
- `*.log`
- `node_modules/`
- generated tokens
- runtime state/log artifacts

## Следующий шаг

1. Не начинать новый Telegram feature-cycle.
2. Не делать GUI split и shared-helper refactor.
3. Если понадобится новый Windows-pass, прогонять тот же exact smoke checklist.
4. Если live client снова пропадёт на adopted машине, сначала лечить extension reload/load-state, а не делать новый runtime redesign.
