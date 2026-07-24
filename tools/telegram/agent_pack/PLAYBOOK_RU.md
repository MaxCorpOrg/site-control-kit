# Практические сценарии агента Telegram

## 1. Если задача про ошибку живого графического интерфейса

- Сначала снять реальные логи и state.
- Не считать panel-harness достаточным доказательством.
- Проверять:
  - panel log;
  - job store;
  - profile locks;
  - combined/session state;
  - subprocess lifecycle.

## 2. Если задача про новую возможность Telegram

- Сначала спросить себя: это runtime tool или platform orchestration?
- Runtime logic не тащить в `tool_platform/gui.py`.
- Если это новый инструмент:
  - дать ему свой runtime;
  - manifest;
  - docs;
  - только потом интеграцию в control center.

## 3. Если задача про несколько платформ

- Не обещать parity раньше adapter/capability layer.
- Сначала сделать:
  - doctor;
  - capabilities;
  - platform metadata в manifests;
  - degraded modes.
- Только потом углублять live automation на Windows/macOS.

## 4. Если задача про устойчивость

- Любой новый workflow должен уметь:
  - status;
  - stop;
  - resume;
  - artifact paths;
  - profile lock discipline.

## 5. Если задача про пользовательский интерфейс

- Панель должна быть thin client.
- Если логика становится сложной, выносить её в workflow/job layer.
- Не прятать критические operator signals в глубине экрана.

## 6. Обязательная проверка после заметной правки

- `PYTHONPATH="$PWD" python3 -m unittest discover -s tests -p 'test_*.py'`
- `python3 -m py_compile ...` для изменённых Python-файлов
- `bash -n ...` для изменённых shell wrappers
- обновить `docs/PROJECT_STATUS_RU.md`
