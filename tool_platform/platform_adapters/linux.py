from __future__ import annotations

from typing import Any

from .base import PlatformAdapter, gui_capability, home_display_capability


class LinuxPlatformAdapter(PlatformAdapter):
    def __init__(self) -> None:
        super().__init__(platform_id="linux", display_name="Linux")

    def capabilities(self) -> dict[str, Any]:
        has_display = bool(home_display_capability().get("available"))
        has_wmctrl = self._command_available("wmctrl")
        has_xlib = self._module_available("Xlib")
        return {
            "gui": gui_capability(),
            "display_session": home_display_capability(),
            "window_automation": {
                # Current Telegram Desktop live lane uses wmctrl for window focus/lookup and
                # python-xlib/XTEST for keys and pointer actions. xdotool is not required.
                "available": has_display and has_wmctrl and has_xlib,
                "detail": "wmctrl + python3-xlib",
            },
            "accessibility": {
                "available": self._module_available("gi"),
                "detail": "python3-gi / AT-SPI",
            },
            "window_screenshot": {
                "available": self._module_available("Xlib") and self._module_available("PIL"),
                "detail": "python3-xlib + Pillow",
            },
            "uri_open": {
                "available": self._command_available("xdg-open"),
                "detail": "xdg-open",
            },
        }
