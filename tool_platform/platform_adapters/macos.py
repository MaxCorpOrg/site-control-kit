from __future__ import annotations

from typing import Any

from .base import PlatformAdapter, gui_capability


class MacOSPlatformAdapter(PlatformAdapter):
    def __init__(self) -> None:
        super().__init__(platform_id="macos", display_name="macOS")

    def capabilities(self) -> dict[str, Any]:
        return {
            "gui": gui_capability(),
            "osascript": {
                "available": self._command_available("osascript"),
                "detail": "AppleScript / osascript",
            },
            "window_automation": {
                "available": self._command_available("osascript"),
                "detail": "AppleScript window control foundation",
            },
            "accessibility": {
                "available": self._command_available("osascript"),
                "detail": "macOS Accessibility foundation",
            },
            "window_screenshot": {
                "available": self._command_available("screencapture"),
                "detail": "screencapture",
            },
            "uri_open": {
                "available": self._command_available("open"),
                "detail": "open",
            },
        }
