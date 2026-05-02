# Tool Platform Integration Guide RU

## Как Подключить Новый Инструмент

### Шаг 1. Создать `tool_manifest.json`

Минимальная форма:

```json
{
  "schema_version": 1,
  "tool_id": "example_tool",
  "display_name": "Example Tool",
  "description": "Short description",
  "kind": "embedded_tool",
  "standalone": false,
  "root_dir": ".",
  "docs": [
    {
      "doc_id": "readme",
      "label": "README",
      "path": "README.md"
    }
  ],
  "actions": [
    {
      "action_id": "help",
      "label": "CLI Help",
      "description": "Show CLI help",
      "argv": ["./bin/example-tool", "--help"],
      "workdir": "."
    }
  ]
}
```

### Шаг 2. Добавить manifest в registry

В `registry/tools.json`:

```json
{
  "manifest_path": "../../tools/example_tool/tool_manifest.json",
  "enabled": true,
  "source_label": "embedded"
}
```

Для отдельного runtime-репозитория допустим absolute path, но предпочтительнее visible wrapper внутри `tools/telegram/`, если инструмент должен быть виден оператору рядом с остальными Telegram workflow.

### Шаг 3. Проверить platform layer

```bash
cd /home/max/site-control-kit/tools/telegram/platform

./bin/tool-platform validate-registry
./bin/tool-platform list-tools
./bin/tool-platform show-tool --tool-id example_tool
```

## Рекомендации По Дизайну Инструмента

- сохранять standalone entrypoint;
- не прятать документацию только в корневой README другого проекта;
- описывать минимум один безопасный action вроде `--help`;
- не регистрировать destructive actions как дефолтные operator actions.

## Текущие Примеры

### Embedded Tool

- `tools/telegram/invite_manager/tool_manifest.json`

### Visible Wrapper Around Standalone Tool

- `tools/telegram/session_runner/tool_manifest.json`

## Как Думать О Масштабировании

Если завтра появится ещё один Telegram-инструмент или вообще не Telegram-инструмент, правильный путь тот же:
- собственная папка или репозиторий;
- свой manifest;
- одна запись в registry.
