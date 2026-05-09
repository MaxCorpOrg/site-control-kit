#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
import importlib


def _is_windows_platform() -> bool:
    return os.name == "nt" or sys.platform.startswith("win")


def _render_startup_error(exc: Exception) -> str:
    text = str(exc).strip() or exc.__class__.__name__
    lowered = f"{exc.__class__.__name__}: {text}".lower()
    if "gi" in lowered or "pygobject" in lowered or "gtk" in lowered:
        return (
            "ERROR: GTK runtime is not available in this Python environment. "
            "On Linux install the system GTK bindings and run "
            "`bash scripts/bootstrap_telegram_workstation.sh --doctor`. "
            "Windows GUI is not supported in production v1."
        )
    return f"ERROR: failed to start telegram GUI: {text}"


def main() -> int:
    if _is_windows_platform():
        print(
            "ERROR: telegram-username-collector GTK GUI is supported only on Linux in production v1. "
            "Use the Windows core/browser wrappers and run the Telegram GUI on a Linux workstation.",
            file=sys.stderr,
        )
        return 2
    try:
        gui_app = importlib.import_module("scripts.telegram_gui.app")
    except Exception as exc:  # pragma: no cover - exercised in broken runtime environments
        print(_render_startup_error(exc), file=sys.stderr)
        return 2
    return int(gui_app.main())


if __name__ == "__main__":
    raise SystemExit(main())
