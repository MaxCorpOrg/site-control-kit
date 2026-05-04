# Telegram Supertool Roadmap RU

Последнее обновление: 2026-05-04

Этот документ фиксирует не текущий багfix-приоритет, а стратегическое направление:
во что превращать Telegram-часть `site-control-kit`, чтобы она стала не набором полезных скриптов,
а устойчивой операторской платформой.

## 1. Где проект силён уже сейчас

Сейчас у проекта уже есть редкая сильная база:

- живой browser bridge с CLI, очередью команд и расширением;
- отдельный Telegram export stack;
- отдельный Telegram invite stack;
- отдельный Telegram Desktop portable stack;
- отдельный standalone session-runner;
- registry-driven control center;
- артефакты прогонов, handoff-документация и unit-покрытие.

То есть проблема проекта уже не в отсутствии возможностей.
Проблема в следующем этапе зрелости:

- как всё это собрать в один устойчивый control plane;
- как не держать оркестрацию в UI-слое;
- как сделать поведение наблюдаемым, воспроизводимым и масштабируемым.

## 2. Главные архитектурные узкие места сейчас

### 2.1. GUI слишком много знает

Сейчас `tool_platform/gui.py` очень большой и несёт на себе сразу несколько ролей:

- сборка интерфейса;
- хранение UI state;
- orchestration add/session/combined режимов;
- запуск subprocess;
- обработка завершения задач;
- рендеринг summary и логов.

Это рабочий practical слой, но не финальная архитектура.
Когда режимов и инструментов станет больше, цена любой правки будет расти слишком быстро.

### 2.2. Состояния и артефакты разложены по нескольким контурам

Сейчас проект использует несколько полезных, но разрозненных хранилищ:

- `state.json` browser bridge;
- `invite_state.json`;
- `session_state.json`;
- combined-state панели в `/tmp/telegram-control-center/...`;
- `runs/*/run.json`;
- `executions/*/execution_record.json`;
- panel log.

Это хорошо для локальной диагностики, но пока нет одного unified index:

- какие задачи сейчас активны;
- к какому профилю они относятся;
- какие артефакты принадлежат какому workflow;
- где последний успешный запуск;
- какой текущий риск у конкретного профиля.

### 2.3. Нет единого job runtime слоя

Сейчас панель фактически управляет subprocess-ами напрямую.
Это дало быстрый результат, но ограничивает рост:

- stop/retry/resume приходится реализовывать режим за режимом;
- живой lifecycle add/session/combined размазан между UI и helper-слоями;
- восстановление после перезапуска панели остаётся хрупким.

### 2.4. Runtime Telegram-инструментов разделён между несколькими формами жизни

Это осознанное решение и его нельзя ломать без причины.
Но на стратегическом горизонте оно создаёт friction:

- часть инструментов embedded;
- session-runner standalone;
- orchestration panel-only;
- часть low-level поведения сидит в scripts, часть в wrappers, часть в manifests.

Это нормально на стадии активной эволюции,
но для “суперинструмента” понадобится более явный контракт рантаймов.

### 2.5. Наблюдаемость уже полезная, но ещё не операторского уровня

Сейчас есть хорошие логи и JSON-артефакты,
но нет одного операторского слоя вида:

- что сейчас происходит;
- на каком шаге мы зависли;
- какой профиль занят;
- какой следующий шаг;
- почему остановились;
- какой run стоит открыть первым.

## 3. Целевая архитектура супер-инструмента

### Слой A. Transport / Device Control

Нижний слой:

- browser bridge;
- Telegram Desktop portable helper;
- X11 / AT-SPI primitives;
- low-level open/click/type/screenshot/status.

Этот слой не должен знать про бизнес-сценарии.

### Слой B. Tool Runtimes

Каждый инструмент живёт как отдельный runtime-модуль:

- export runtime;
- invite runtime;
- session runtime;
- profile runtime;
- future tools.

У каждого runtime должен быть единый контракт:

- `plan`
- `run`
- `stop`
- `status`
- `artifacts`
- `resume`

### Слой C. Workflow Engine

Отдельный orchestration-слой, не в Tkinter GUI:

- combined flow;
- chain of runs;
- alternating step patterns;
- retry policies;
- preconditions;
- profile locks;
- transition rules.

То, что сейчас partially живёт в `gui.py`, стратегически нужно вынести сюда.

### Слой D. Unified Job Store

Нужен общий индекс задач, а не только набор раздельных JSON-файлов.

Минимальный target:

- `job_id`
- `tool_id`
- `profile_id`
- `status`
- `phase`
- `started_at`
- `updated_at`
- `last_error`
- `artifact_paths`

Это может быть:

- сначала один unified JSON index;
- потом SQLite, если станет тесно.

### Слой E. Operator Control Center

Панель должна быть тоньше:

- выбирать профиль;
- выбирать режим;
- запускать job;
- показывать историю;
- показывать следующее действие;
- давать stop/retry/resume/open-artifacts.

То есть UI должен стать клиентом workflow engine, а не местом, где живёт логика процесса.

### Слой F. Policy / Safety Layer

Отдельный слой правил:

- какие действия можно делать на профиле;
- лимиты отправки;
- лимиты добавления;
- safe/draft/confirm-send;
- profile lock;
- forbidden parallel runs;
- consent boundaries.

Сейчас часть этого уже есть фактически, но пока не как единый policy contract.

## 4. Что стоит улучшать в первую очередь

### Приоритет 1. Довести стабильность текущего control center

Пока живой баг `Совместного режима` не закрыт, новые большие фичи будут только увеличивать хрупкость.

Минимум:

- воспроизвести реальный live GUI bug;
- сравнить panel-harness и живой subprocess lifecycle;
- стабилизировать combined-state;
- убрать любые расхождения между “что видит пользователь” и “что реально запущено”.

### Приоритет 2. Вынести orchestration из `gui.py`

Самый сильный следующий архитектурный шаг.

Нужно выделить отдельный слой, условно:

- `tool_platform/workflows.py`
- `tool_platform/jobs.py`

и вынести туда:

- combined flow transitions;
- start/complete/error transitions;
- profile locks;
- pattern cursor logic;
- stop/retry/resume semantics.

Это резко уменьшит сложность UI и облегчит тестирование.

### Приоритет 3. Сделать unified job index

Нужна одна понятная “карта мира” по всем Telegram workflow:

- активные задачи;
- последние успешные задачи;
- задачи с ошибками;
- привязка к профилю;
- пути к последним артефактам.

Это даст:

- history center;
- быстрый resume;
- operator audit trail;
- будущий API для headless режима.

### Приоритет 4. Сделать profile-centric workspace

Сейчас профиль уже главный объект панели.
Следующий шаг: сделать вокруг него workspace:

- профиль;
- его статусы;
- его последние add-runs;
- его последние session-runs;
- его ограничения;
- его health;
- его историю действий.

Тогда оператор будет мыслить не “какой скрипт сейчас запустить”,
а “что происходит с этим конкретным Telegram-аккаунтом”.

## 5. Что можно добавить, чтобы это стало реально супер-инструментом

### 5.1. Unified Timeline

Один экран истории по профилю:

- добавления контактов;
- сессии;
- сообщения;
- ошибки;
- стопы;
- ручные вмешательства;
- ссылки на run.json / screenshots / logs.

### 5.2. Replay / Explain Mode

Для каждой задачи:

- что планировалось;
- что реально произошло;
- на каком шаге остановились;
- какие evidence есть.

Это сильно ускорит отладку и handoff.

### 5.3. Scenario Builder

Надстроечный уровень поверх combined mode:

- добавить 2 контакта;
- потом 1 session cycle;
- потом отправить 2 сообщения;
- потом пауза;
- потом ещё один batch.

Сначала можно держать это в виде JSON/DSL, без тяжёлого визуального редактора.

### 5.4. Scheduler

Нужен режим “запусти позже”:

- по времени;
- по профилю;
- по сценарию;
- с лимитами и safe guard.

Это сразу переводит систему из “ручного пульта” в semi-automatic control plane.

### 5.5. Health Center

Отдельный обзор по профилям и рантаймам:

- Telegram profile running / stopped;
- окно найдено / не найдено;
- AT-SPI доступен / нет;
- browser bridge жив / нет;
- session-runner repo доступен / нет;
- последний успешный workflow по каждому инструменту.

### 5.6. Recovery Recipes

Автоматические рецепты восстановления:

- перезапусти portable;
- пересними окно;
- обнови accessibility tree;
- открой нужный чат снова;
- пересобери runtime config;
- повтори последний шаг.

### 5.7. Headless Control API

Когда platform layer стабилизируется, полезно дать API поверх Telegram workflows:

- создать job;
- получить status;
- остановить job;
- получить artifacts.

Это сделает панель не единственной точкой входа.

### 5.8. Tool SDK

Если действительно хочется “платформу под другие инструменты”,
то нужен не просто manifest loader, а маленький SDK/contract:

- как инструмент объявляет actions;
- как публикует job status;
- как отдаёт artifacts;
- как сообщает `resume` и `stop`.

## 6. Самые сильные конкретные улучшения по текущему коду

### 6.1. Разрезать `tool_platform/gui.py`

Сейчас это явный hotspot.
Практический целевой разрез:

- `tool_platform/gui_view.py`
- `tool_platform/gui_state.py`
- `tool_platform/gui_actions.py`
- `tool_platform/workflows.py`

Не ради красоты, а чтобы:

- combined mode тестировался без Tk;
- stop/retry/resume логика жила вне UI;
- панель перестала быть центром бизнес-логики.

### 6.2. Стандартизировать payload статусов

Разные Telegram-инструменты должны возвращать один более ровный минимум:

- `status`
- `phase`
- `summary`
- `artifact_paths`
- `next_hint`
- `recoverable`

Тогда panel code станет проще и менее режим-специфичным.

### 6.3. Сделать единый artifact index

Сейчас артефакты сильные, но разрозненные.
Нужен единый слой:

- открыть последний run;
- открыть последний screenshot;
- открыть последний error;
- открыть последний execution record.

### 6.4. Ввести profile lock manager как отдельный модуль

Сейчас профильные конфликты уже учитываются.
Но это должно стать отдельной сущностью:

- кто держит lock;
- когда он взят;
- по какому tool_id;
- когда можно force-release.

### 6.5. Отвязать combined flow от “временного panel-state”

`/tmp` удобен, но для супер-инструмента combined/job state лучше сделать стабильнее:

- либо под project data root;
- либо через unified job index;
- либо через explicit profile workspace.

## 7. Рекомендуемый порядок развития

### Этап 1. Stabilize

- закрыть баг живого combined mode;
- выровнять live GUI и harness;
- сохранить простоту панели.

### Этап 2. Orchestration Core

- вынести workflow logic из GUI;
- ввести unified job model;
- стандартизировать transitions и stop/retry/resume.

### Этап 3. Observability

- unified timeline;
- artifact index;
- health center;
- explain/replay view.

### Этап 4. Power Features

- scheduler;
- scenario builder;
- headless API;
- tool SDK;
- подключение новых Telegram workflow по одному контракту.

## 8. Что делать следующим практическим шагом

Не начинать сразу с большого рефактора всего проекта.

Самый сильный следующий шаг после фикса текущего live GUI бага:

1. выделить отдельный orchestration-модуль для combined/session/contact flows;
2. ввести unified in-project job index;
3. перевести панель на чтение этого слоя, а не на прямое владение subprocess lifecycle.

Именно это даст больше всего пользы на единицу сложности.
