from __future__ import annotations

import sys
from typing import Any

from .base import PlatformAdapter, capability_warnings, gui_capability
from .linux import LinuxPlatformAdapter
from .macos import MacOSPlatformAdapter
from .windows import WindowsPlatformAdapter


def current_platform_id() -> str:
    if sys.platform.startswith("linux"):
        return "linux"
    if sys.platform == "darwin":
        return "macos"
    if sys.platform in {"win32", "cygwin"}:
        return "windows"
    return "unknown"


def get_platform_adapter(platform_id: str | None = None) -> PlatformAdapter:
    resolved = platform_id or current_platform_id()
    if resolved == "linux":
        return LinuxPlatformAdapter()
    if resolved == "windows":
        return WindowsPlatformAdapter()
    if resolved == "macos":
        return MacOSPlatformAdapter()
    class GenericPlatformAdapter(PlatformAdapter):
        def capabilities(self) -> dict[str, Any]:
            return {
                "gui": gui_capability(),
                "window_automation": {"available": False, "detail": "unknown_platform"},
                "accessibility": {"available": False, "detail": "unknown_platform"},
                "window_screenshot": {"available": False, "detail": "unknown_platform"},
                "uri_open": {"available": False, "detail": "unknown_platform"},
            }

    return GenericPlatformAdapter(platform_id=resolved, display_name=resolved.capitalize())


def platform_capabilities(platform_id: str | None = None) -> dict[str, Any]:
    adapter = get_platform_adapter(platform_id)
    return adapter.capabilities()


def platform_capability_warnings(platform_id: str | None = None) -> list[str]:
    return capability_warnings(platform_capabilities(platform_id))


def platform_doctor_report(platform_id: str | None = None) -> dict[str, Any]:
    adapter = get_platform_adapter(platform_id)
    report = adapter.doctor()
    report["current_platform_id"] = current_platform_id()
    report["warnings"] = capability_warnings(report["capabilities"])
    return report
