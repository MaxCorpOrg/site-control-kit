# Changelog

## 2026-05-11

### Windows Core Smoke And End-Of-Day Checkpoint

- Подтверждён narrow Windows smoke для `telegram-username-collector` и core/browser wrappers на `C:\site-control-kit-win-smoke`.
- `scripts\start_hub.cmd` снова поднимает hub на Windows без traceback.
- `python -m webcontrol runtime-env --format json --no-create` показывает `legacy-adopted` runtime, `token_file` source и реальные runtime paths.
- `browser.cmd status` и `browser.cmd tabs` подтверждены на live client `client-win-edge-manual-20260510`.
- `telegram-username-collector` на Windows подтверждён как controlled fast-fail launcher, а не как GUI runtime entrypoint.
- После rebase на актуальный `main` внесён минимальный cross-platform fix:
  - `scripts/telegram_product_runtime.py` больше не падает без определяемого home directory;
  - `tests/test_telegram_product_runtime.py` больше не требует POSIX execute bit на Windows-host.
- End-of-day docs синхронизированы:
  - `README.md`
  - `docs/ARCHITECTURE.md`
  - `NEXT_STEPS.md`
  - `AGENTS.md`
  - handoff/state docs

### Проверки

- `git diff --check`
- `python -m unittest discover -s tests -p "test_*.py"`
- `python -m webcontrol --help`
- `python -m webcontrol browser --help`
- `python -m webcontrol runtime-env --format json --no-create`
- `.\browser.cmd status`
- `.\browser.cmd tabs`
- `.\telegram-username-collector.cmd`

Финальный итог verify после rebase: `303 tests OK`.

Во время финального end-of-day verify browser client один раз успел стать stale/offline; recovery снова остался runtime-only:

- перезапуск Edge debug profile с `--disable-extensions-except=<repo>\extension`
- и `--load-extension=<repo>\extension`

После этого `browser.cmd status` и `browser.cmd tabs` снова стали зелёными.

### Риски

- adopted Edge debug profile может повторно потерять active unpacked-extension load state;
- fresh project-local runtime path по-прежнему не подтверждён на машине с existing `%USERPROFILE%\.site-control-kit`.

## 2026-05-10

### Windows Core Smoke + Release Confidence

- Починен Windows PowerShell hub launcher path.
- Усилен runtime/config слой и диагностика `runtime-env`.
- Добавлены Windows-safe launcher paths и no-GTK fast-fail contract для Telegram GUI entrypoints.
- Подтверждён live browser client после Windows smoke на adopted runtime.
