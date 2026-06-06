# Next Steps

Дата: 2026-06-06

## Текущий baseline

- Ветка: `main`
- Основной операторский путь: `GTK GUI -> Primary tdata`
- Ready direct helper source на этом хосте:
  - `/home/max/site-control-kit/TG_CONTACT/4/tdata-003/tdata`
- `default_user` не менять без отдельной причины
- `AK2 live 959756539365` не потерян, но его portable helper-clone перед следующим export ещё требует readiness refresh

## Что уже подтверждено

- Unified `public_phones` flow теперь согласован в helper, GUI, history и `INDEX.md`:
  - `phones_found` = total unique phones
  - `private_phones_found` = private-only split
  - overlap rule = `public wins`
- Полный suite зелёный:
  - `python3 -m unittest discover -s tests -p 'test_*.py'` -> `319 tests OK`, `2 skipped`
- Базовые runtime-check команды зелёные:
  - `python3 -m webcontrol --help`
  - `python3 -m webcontrol browser --help`
- `python3 -m py_compile` по затронутым Telegram-файлам -> OK
- GTK GUI видим на `DISPLAY=:0`
- Live `Quick Check` на ready source уже сохранён:
  - run `20260606T074214Z`
  - `phones_found=1`
  - `private_phones_found=1`
  - `/tmp/site-control-live-private-phones-1_phones.{md,txt,json,private.txt,private.json}`
- Full-history run на том же source уже завершён:
  - чат `НаДопинге 2.0 ЧАТ | Бодибилдинг | Фитнес | Спорт Фармакология`
  - run `20260606T092821Z`
  - `status=done`
  - `history_messages_scanned=187923`
  - `phones_found=145`
  - `public_count=62`
  - `private_phones_found=83`
  - `/tmp/tg4_nadopinge_full_history_phones_20260606_phones.{md,txt,json,private.txt,private.json}`
  - `/home/max/.site-control-kit/telegram_workspace/runs/20260606T092821Z/{summary.json,artifacts.json,events.jsonl}`

## Что осталось

- Если нужен следующий live-pass без recovery-работ, идти уже через ready source `TG_CONTACT 4`:
  - либо анализировать текущие `145` номеров,
  - либо брать следующий чат тем же direct helper/API path
- Если нужен именно AK2-run:
  - сначала вернуть helper-clone профиля `AK2 live 959756539365` в `ready for export`
- Не расширять `public_phones` на bridge/CDP/web fallback без отдельной задачи

## Следующий узкий контур

```bash
cd /home/max/site-control-kit
/home/max/telegram-api-collector/.venv/bin/python scripts/telegram_tdata_helper.py export-public-phones \
  --tdata "/home/max/site-control-kit/TG_CONTACT/4/tdata-003/tdata" \
  --session /tmp/tg4_public_phones_smoke.session \
  --chat-ref -1002465948544 \
  --history-limit 50 \
  --progress-every 25
```

Если нужен GUI-path:
1. Запустить `scripts/telegram_members_export_gui.py`
2. Выбрать ready `Primary tdata` source
3. Оставить `Full History` или `Quick Check`
4. Сохранить `*_phones.md`, `*_phones.txt`, `*_phones.json`, `*.private.*`, `summary.json`, `artifacts.json`, `events.jsonl`

## Что не перепутать

- Для прямого helper-run использовать collector venv:
  - `/home/max/telegram-api-collector/.venv/bin/python`
- Голый системный `python3` может дать:
  - `Missing opentele dependency. Run this helper via the collector venv.`
- Generated `artifacts/telegram_exports/INDEX.md` не тащить в commit, если это только локальный live-след
- Не коммитить:
  - `.site-control-kit/`
  - `TG_CONTACT/`
  - `dist/`
  - `*.log`
  - токены, ключи, временные сессии
