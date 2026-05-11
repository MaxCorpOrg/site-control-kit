# Next Steps

## Текущий baseline

- Ветка: `main`
- Рабочая машина последнего узкого smoke: `C:\site-control-kit-win-smoke`
- Подтверждённый режим runtime на этой машине: `legacy-adopted`
- Последний узкий verify-контур:
  - `python -m unittest discover -s tests -p "test_*.py"`
  - `python -m webcontrol --help`
  - `python -m webcontrol browser --help`
  - `python -m webcontrol runtime-env --format json --no-create`
  - `.\browser.cmd status`
  - `.\browser.cmd tabs`
  - `.\telegram-username-collector.cmd`

## Что уже сделано

- Windows hub wrapper больше не падает на PowerShell runtime-env glue path.
- `runtime-env` показывает runtime mode, token source и реальные state/log/token paths.
- Windows/Git Bash launcher path больше не упирается в WindowsApps `python3` stub.
- `telegram-username-collector` и legacy GUI entrypoints на Windows дают controlled fast-fail вместо GTK/import traceback.
- На adopted Windows-машине подтверждён live browser client после recovery extension load state.

## Что осталось

- Главный оставшийся риск сейчас операционный, а не кодовый:
  - adopted Edge debug profile может снова потерять active unpacked-extension load state.
- На текущей машине не подтверждён fresh project-local runtime path, потому что existing `%USERPROFILE%\.site-control-kit` честно переводит сценарий в `legacy-adopted`.

## Следующий узкий шаг

1. Не начинать новый Telegram feature-cycle.
2. Не делать новый GUI split и shared-helper refactor.
3. Если нужен следующий Windows-pass, прогонять тот же exact smoke checklist и сначала лечить extension reload/load-state, а не делать новый wrapper/runtime redesign.
4. Если нужен именно fresh-runtime verify, делать его на отдельной Windows-среде без существующего `%USERPROFILE%\.site-control-kit`.

## Как входить следующему агенту

1. Прочитать `AGENT_START_HERE.md`.
2. Прочитать `CODEX_STATE.md`.
3. Прочитать последний файл в `docs/checkpoints/`.
4. Проверить `git status --short --branch` и `git remote -v`.
5. Не тащить в commit `.env`, `.site-control-kit/`, `var/`, `*.log`, `node_modules/` и runtime-артефакты.
6. Перед browser-задачами сначала проверять `.\browser.cmd status` и `.\browser.cmd tabs`.
