#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import sys
import importlib
from typing import Any

try:
    from .telegram_product_runtime import create_desktop_shortcut, format_doctor_report, gather_doctor_report
except ImportError:  # pragma: no cover - direct script execution fallback
    from telegram_product_runtime import create_desktop_shortcut, format_doctor_report, gather_doctor_report


def _is_windows_platform() -> bool:
    return os.name == "nt" or sys.platform.startswith("win")


def _render_startup_error(exc: Exception) -> str:
    text = str(exc).strip() or exc.__class__.__name__
    lowered = f"{exc.__class__.__name__}: {text}".lower()
    if "gi" in lowered or "pygobject" in lowered or "gtk" in lowered:
        return (
            "ERROR: GTK runtime is not available in this Python environment. "
            "Run `telegram-username-collector --doctor` first. "
            "If GTK is still missing, on Linux install the system GTK bindings and run "
            "`bash scripts/bootstrap_telegram_workstation.sh --doctor`. "
            "Windows GUI is not supported in production v1."
        )
    return f"ERROR: failed to start telegram GUI: {text}"


UI_SCALE_ENV = "TELEGRAM_GUI_SCALE"


def _parse_ui_scale(raw: str) -> str:
    try:
        value = float(str(raw).strip())
    except (TypeError, ValueError) as exc:
        raise argparse.ArgumentTypeError("scale must be a number between 0.75 and 1.75") from exc
    if value < 0.75 or value > 1.75:
        raise argparse.ArgumentTypeError("scale must be between 0.75 and 1.75")
    return f"{value:.2f}".rstrip("0").rstrip(".")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="telegram-username-collector",
        description="Telegram Username Collector launcher",
    )
    parser.add_argument(
        "--doctor",
        action="store_true",
        help="print product/runtime diagnostics without starting the GTK window",
    )
    parser.add_argument(
        "--create-desktop-shortcut",
        action="store_true",
        help="create a desktop launcher for the current Linux user",
    )
    parser.add_argument(
        "--ui-scale",
        type=_parse_ui_scale,
        metavar="FACTOR",
        help="scale the GTK panel, for example 0.9, 1.0, 1.25 or 1.5",
    )
    return parser


def _apply_launcher_options(args: Any) -> None:
    if getattr(args, "ui_scale", None):
        os.environ[UI_SCALE_ENV] = str(args.ui_scale)


def main(argv: list[str] | None = None) -> int:
    raw_args = list(sys.argv[1:] if argv is None else argv)
    parser = _build_parser()
    args, remaining = parser.parse_known_args(raw_args)
    _apply_launcher_options(args)

    if _is_windows_platform():
        print(
            "ERROR: telegram-username-collector GTK GUI is supported only on Linux in production v1. "
            "Use the Windows core/browser wrappers and run the Telegram GUI on a Linux workstation.",
            file=sys.stderr,
        )
        return 2
    if args.doctor:
        print(format_doctor_report(gather_doctor_report(mutate=True)), end="")
        return 0
    if args.create_desktop_shortcut:
        try:
            shortcut_path = create_desktop_shortcut()
        except Exception as exc:
            print(f"ERROR: failed to create desktop shortcut: {exc}", file=sys.stderr)
            return 1
        print(str(shortcut_path))
        return 0
    try:
        gui_app = importlib.import_module("scripts.telegram_gui.app")
    except Exception as exc:  # pragma: no cover - exercised in broken runtime environments
        print(_render_startup_error(exc), file=sys.stderr)
        return 2
    original_argv = list(sys.argv)
    try:
        sys.argv = [original_argv[0], *remaining]
        return int(gui_app.main())
    finally:
        sys.argv = original_argv


if __name__ == "__main__":
    raise SystemExit(main())
