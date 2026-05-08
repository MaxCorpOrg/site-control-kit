#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

if __package__:
    from .telegram_gui import app as _app
else:
    script_dir = Path(__file__).resolve().parent
    repo_root = script_dir.parent
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    from scripts.telegram_gui import app as _app

sys.modules[__name__] = _app


if __name__ == "__main__":
    raise SystemExit(_app.main())
