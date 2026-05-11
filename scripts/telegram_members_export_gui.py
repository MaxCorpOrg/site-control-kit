#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
from pathlib import Path

WINDOWS_GUI_EXIT_CODE = 2
WINDOWS_GUI_UNSUPPORTED_MESSAGE = (
    "ERROR: telegram-username-collector GTK GUI is supported only on Linux in production v1. "
    "Use the Windows core/browser wrappers and run the Telegram GUI on a Linux workstation."
)


def _is_windows_platform() -> bool:
    return os.name == "nt" or sys.platform.startswith("win")


def _windows_fast_fail() -> int:
    print(WINDOWS_GUI_UNSUPPORTED_MESSAGE, file=sys.stderr)
    return WINDOWS_GUI_EXIT_CODE


if __name__ == "__main__" and _is_windows_platform():
    raise SystemExit(_windows_fast_fail())

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
