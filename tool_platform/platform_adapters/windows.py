from __future__ import annotations

from typing import Any

from .base import PlatformAdapter, gui_capability


class WindowsPlatformAdapter(PlatformAdapter):
    def __init__(self) -> None:
        super().__init__(platform_id="windows", display_name="Windows")

    def capabilities(self) -> dict[str, Any]:
        return {
            "gui": gui_capability(),
            "powershell": {
                "available": self._command_available("powershell") or self._command_available("pwsh"),
                "detail": "PowerShell / pwsh",
            },
            "window_automation": {
                "available": self._module_available("ctypes"),
                "detail": "Win32 / UI Automation foundation",
            },
            "accessibility": {
                "available": self._module_available("ctypes"),
                "detail": "Windows accessibility foundation",
            },
            "window_screenshot": {
                "available": self._module_available("PIL"),
                "detail": "Pillow",
            },
            "uri_open": {
                "available": self._command_available("powershell") or self._command_available("pwsh"),
                "detail": "Start-Process",
            },
        }
