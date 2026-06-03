# CHECKPOINT 2026-06-02: AK2 Cosmetology Public Phones

## Что сделано
- Пройден живой GTK/operator batch `AK2 live 959756539365 -> Primary tdata -> Сбор открытых номеров -> Full History`.
- `default_user` не менялся.
- Batch остановлен по просьбе пользователя после 4-го чата.

## Важный найденный факт
- Первый full-history запуск упал не из-за Telegram auth и не из-за GUI:
  - `export-public-phones` ошибочно использовал `TELEGRAM_TDATA_LIST_TIMEOUT_SEC`
  - точный failure:
    - `/home/max/Документы/ак2/живой_тест_номеров/ak2_cosmetology_public_phones_full_history_summary_20260602T110234Z.json`
    - error: `tdata helper timed out after 30s: export-public-phones`
- Fix уже внесён:
  - `scripts/telegram_gui/app.py`
  - `scripts/telegram_gui/ui/window.py`
  - `tests/test_telegram_members_export_gui.py`

## Verify фикса
- `python3 -m py_compile scripts/telegram_gui/app.py scripts/telegram_gui/ui/window.py tests/test_telegram_members_export_gui.py` -> OK
- `python3 -m unittest tests.test_telegram_members_export_gui` -> `44 tests OK`, `2 skipped`

## Живые результаты batch
- `Косметология`
  - `status=done`
  - `phones_found=8`
  - `history_messages_scanned=1531`
  - run: `20260602T110512Z`
- `КОСМЕТОЛОГИЯ ЧАТ`
  - `status=done`
  - `phones_found=3`
  - `history_messages_scanned=1383`
  - run: `20260602T111811Z`
- `ЧАТ КОСМЕТОЛОГОВ +1`
  - `status=done`
  - `phones_found=2`
  - `history_messages_scanned=6238`
  - run: `20260602T113010Z`
- `Форум Косметология | Дерматология`
  - `status=partial`
  - `phones_found=2`
  - `history_messages_scanned=2211`
  - run: `20260602T113456Z`
- `Косметологи Чат | Сообщество Профессионалов`
  - не запускался

## Главные артефакты
- Batch summary:
  - `/home/max/Документы/ак2/живой_тест_номеров/ak2_cosmetology_public_phones_full_history_summary_20260602T110438Z.json`
  - `/home/max/Документы/ак2/живой_тест_номеров/ak2_cosmetology_public_phones_full_history_summary_20260602T110438Z.md`
- Shared action log:
  - `/home/max/.site-control-kit/telegram_workspace/logs/gui_ak2_cosmetology_full_history_phones_20260602T110438Z.log`
- Completed chat outputs:
  - `/home/max/Документы/ак2/живой_тест_номеров/ak2_cosmetology_01_kosmetologi_chat_full_history_phones.{md,txt,json}`
  - `/home/max/Документы/ак2/живой_тест_номеров/ak2_cosmetology_02_cosmetology_chat_full_history_phones.{md,txt,json}`
  - `/home/max/Документы/ак2/живой_тест_номеров/ak2_cosmetology_03_cosmetology_help_full_history_phones.{md,txt,json}`
- Partial chat outputs:
  - `/home/max/Документы/ак2/живой_тест_номеров/ak2_cosmetology_04_chatkosmetologa_full_history_phones.{md,txt,json}`

## Следующий шаг
- Повторить 4-й чат без остановки.
- Затем прогнать 5-й чат.
- После этого отдельно подтвердить, что после code-fix `export-public-phones` больше не требует искусственно большого `TELEGRAM_TDATA_LIST_TIMEOUT_SEC`.
