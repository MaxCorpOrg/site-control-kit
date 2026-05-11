# Windows Smoke Handoff RU

Точный handoff для Windows-агента, который должен проверить только `Windows core smoke` вокруг `telegram-username-collector`.

## Scope

- Цель этого handoff: подтвердить Windows install/runtime/wrapper contract и Windows fast-fail contract launcher-а.
- Это не полный release-pass всей платформы и не новый Telegram development cycle.
- Разрешён только один вид расширения scope: минимальный root-cause fix, если blocker найден именно в Windows wrappers, install story или runtime resolution.

## Источники Правды

- `AGENT_START_HERE.md`
- `CODEX_STATE.md`
- `README.md`
- `docs/INSTALL_OTHER_DEVICES_RU.md`
- `scripts/telegram_username_collector_launcher.py`

## Что Не Делать

- Не начинать новый Telegram feature-cycle.
- Не делать новый GUI split.
- Не рефакторить shared helpers.
- Не запускать Linux-only verify как часть этого smoke:
  - `bash scripts/bootstrap_telegram_workstation.sh --doctor`
  - Linux GTK smoke
  - полный multi-platform verify-pass
- Не трогать `.codex`, `TG_CONTACT/`, `.site-control-kit/`, `var/`, runtime state, private logs и `artifacts/telegram_exports/INDEX.md`, если нет отдельного явного запроса.

## Shell И Директория

- Install можно делать из PowerShell.
- Сам smoke нужно фиксировать из `cmd.exe` в Windows Terminal.
- Предпочтительный checkout path: путь с кириллицей, чтобы сразу проверить UTF-8 rendering.
- Все команды выполнять из корня репозитория.

## Exact Procedure

### 1. Checkout

```cmd
git clone https://github.com/MaxCorpOrg/site-control-kit.git "%USERPROFILE%\Desktop\site-control-kit-utf8-тест"
cd /d "%USERPROFILE%\Desktop\site-control-kit-utf8-тест"
git checkout main
git pull --ff-only origin main
git rev-parse HEAD
git status --short --branch
```

Успех:
- checkout на `main`;
- рабочее дерево чистое или явно зафиксировано в отчёте.

Blocker:
- нет `git`;
- checkout повреждён;
- рабочая директория непригодна для запуска.

Limitation:
- если уже существует `%USERPROFILE%\.site-control-kit`, это допустимо, но тогда сценарий нужно явно пометить как `adopted legacy runtime`, а не `fresh auto-create`.

### 2. Install

Если `python.exe` отсутствует в `PATH`, допустима замена `python -m ...` на `py -3 -m ...`, но это нужно явно записать как environment deviation.

```cmd
py -3.11 -m pip install -r requirements.txt
py -3.11 -m pip install -e .
py -3.11 --version
where python
where py
```

Успех:
- editable install завершён;
- console script `telegram-username-collector` доступен.

Blocker:
- install падает;
- console script не появляется;
- зависимости требуют ручного Linux/GTK обхода для Windows smoke.

### 3. Hub Start

Открыть `Terminal A` в том же repo root и оставить хаб в foreground:

```cmd
cd /d "%USERPROFILE%\Desktop\site-control-kit-utf8-тест"
scripts\start_hub.cmd
```

Immediate artifacts expected:
- `.site-control-kit\generated_token.txt`
- `var\site-control-kit\logs\hub.log`
- `var\site-control-kit\logs\runtime_events.jsonl`

Не обязательно сразу:
- `var\site-control-kit\state\state.json` может появиться только после первого heartbeat или сохранения state.

Успех:
- нет traceback;
- PowerShell wrapper не падает;
- hub поднимается и остаётся в рабочем состоянии.

Blocker:
- non-zero exit;
- PowerShell exception;
- raw traceback;
- token/runtime resolution failure.

### 4. Core Smoke Before Extension

В `Terminal B` прогнать exact documented smoke и зафиксировать первый результат как есть:

```cmd
cd /d "%USERPROFILE%\Desktop\site-control-kit-utf8-тест"
browser.cmd status
browser.cmd tabs
python -m webcontrol --help
python -m webcontrol browser --help
python -m webcontrol runtime-env --format json --no-create
```

Успех для help/runtime:
- help печатается без traceback;
- `runtime-env` печатает валидный JSON.

Ожидаемый промежуточный результат:
- до подключения extension `browser.cmd status` и `browser.cmd tabs` могут отвечать сообщением уровня `No connected browser clients...`.
- Это не blocker на этом шаге.

Blocker:
- `browser.cmd` или `python -m webcontrol ...` падают из-за wrapper/runtime/token issues;
- malformed JSON;
- hardcoded machine-specific path вместо resolved runtime.

### 5. Minimal Extension Install And Retry

Если `browser.cmd status` или `browser.cmd tabs` не дали полезный результат из-за отсутствия live client, сделать только минимальную установку extension и повторить только эти команды:

```cmd
type .site-control-kit\generated_token.txt
browser.cmd status
browser.cmd tabs
```

Manual browser steps:
- Открыть `chrome://extensions` или `edge://extensions`.
- Включить `Developer mode`.
- Нажать `Load unpacked`.
- Выбрать `<repo-root>\extension`.
- В `Options` выставить:
  - `Server URL = http://127.0.0.1:8765`
  - `Access Token = значение из .site-control-kit\generated_token.txt`
- Подождать heartbeat и повторить `browser.cmd status` и `browser.cmd tabs`.

Успех после установки extension:
- `browser.cmd status` печатает JSON с `"ok": true` и объектом `client`;
- `browser.cmd tabs` печатает JSON с `"ok": true`, `client_id` и списком `tabs`.

Blocker:
- даже после установки extension wrappers не выходят на рабочий клиент;
- остаются token mismatch / runtime-path mismatch / traceback.

### 6. Runtime Scenario And UTF-8

Это обязательная часть smoke evidence:

```cmd
python -X utf8 -c "from pathlib import Path; import json; paths=['.site-control-kit','var/site-control-kit','var/site-control-kit/logs','var/site-control-kit/reports','var/site-control-kit/state','var/site-control-kit/browser-profile','var/site-control-kit/firefox-profile','var/site-control-kit/telegram_workspace','var/site-control-kit/telegram_workspace/registry','var/site-control-kit/telegram_workspace/managed_helper','var/site-control-kit/reports/telegram_exports']; print(json.dumps({'msg':'Проверка UTF-8','cwd':str(Path.cwd()),'exists':{p:Path(p).exists() for p in paths}}, ensure_ascii=False, indent=2))"
python -m webcontrol runtime-env --format json --no-create
```

Успех в `fresh project-local` scenario:
- `SITECTL_RUNTIME_ROOT` указывает в `var\site-control-kit` внутри repo;
- каталоги из списка существуют;
- кириллица в `cwd` и `msg` читается без mojibake.

Успех в `adopted legacy runtime` scenario:
- `SITECTL_RUNTIME_ROOT` указывает на `%USERPROFILE%\.site-control-kit`;
- внутри repo есть `.site-control-kit\local.yaml`;
- это не blocker, но fresh auto-create в таком прогоне считать неподтверждённым.

Blocker:
- runtime уходит в непредсказуемый foreign path;
- JSON сломан;
- runtime не создаётся в fresh scenario;
- UTF-8 ломается в stdout/stderr.

### 7. Launcher Fast-Fail

```cmd
telegram-username-collector
```

Успех:
- процесс завершается быстро;
- exit code = `2`;
- нет traceback;
- stderr по смыслу совпадает с текущим contract:
  - Windows GTK GUI не поддерживается в production v1;
  - использовать Windows core/browser wrappers;
  - Telegram GUI запускать на Linux workstation.

Blocker:
- появляется GTK окно;
- идёт import/build traceback;
- launcher зависает вместо controlled fast-fail.

## Как Классифицировать Результат

- Успешный результат этого handoff-а: доказан Windows install/runtime/wrapper contract и Windows fast-fail contract launcher-а.
- Первый `browser.cmd status/tabs` без heartbeat не считать blocker-ом.
- `adopted legacy runtime` сам по себе не blocker.
- Blocker only if:
  - wrapper/install/runtime story broken;
  - launcher contract broken;
  - после установки extension browser wrappers всё ещё не работают.

## Report Format

- `Windows version`
- `shell`
- `python version`
- `repo path`
- `fresh` или `adopted legacy`
- точный результат каждой команды из smoke checklist:
  - exit code
  - короткий stdout/stderr summary
- что показал `runtime-env --format json --no-create`:
  - `SITECTL_RUNTIME_ROOT`
  - `SITECTL_STATE_FILE`
  - `SITECTL_LOG_DIR`
  - `SITECTL_REPORTS_ROOT`
  - `TELEGRAM_WORKSPACE_ROOT`
  - наличие `SITECTL_TOKEN`
- какие runtime dirs реально создались сразу после `scripts\start_hub.cmd`
- появились ли:
  - `.site-control-kit\generated_token.txt`
  - `var\site-control-kit\logs\hub.log`
  - `var\site-control-kit\logs\runtime_events.jsonl`
- появился ли `state.json` сразу или только после heartbeat
- как выглядел fast-fail у `telegram-username-collector`
- был ли mojibake
- были ли нужны правки кода
- какие handoff/docs обновлены
- что осталось риском
- какой следующий шаг

## Assumptions

- Для smoke использовать `scripts\start_hub.cmd` и root `browser.cmd`.
- Если на машине есть только `py`, а не `python`, это фиксируется как environment deviation, а не как повод рефакторить repo.
- Если нужен уже не узкий Windows smoke, а полный release-confidence pass всей платформы, это нужно ставить отдельной задачей.
