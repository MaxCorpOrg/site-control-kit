from __future__ import annotations

from typing import Any

from .base import PlatformAdapter, gui_capability, home_display_capability


class LinuxPlatformAdapter(PlatformAdapter):
    def __init__(self) -> None:
        super().__init__(platform_id="linux", display_name="Linux")

    def capabilities(self) -> dict[str, Any]:
        display_session = home_display_capability()
        has_display = bool(display_session.get("available"))
        has_wmctrl = self._command_available("wmctrl")
        has_xlib = self._module_available("Xlib")
        wayland_warning = [
            "Wayland detected",
            "X11 primitives available",
            "safe attach still requires profile-owned X11 window confirmation",
        ] if str(display_session.get("session_type") or "") == "wayland" else []
        return {
            "gui": gui_capability(),
            "display_session": display_session,
            "window_automation": {
                # Current Telegram Desktop live lane uses wmctrl for window focus/lookup and
                # python-xlib/XTEST for keys and pointer actions. xdotool is not required.
                "available": has_display and has_wmctrl and has_xlib,
                "detail": "wmctrl + python3-xlib"
                + (" (Wayland session: attach proof still depends on profile-owned X11 window)" if wayland_warning else ""),
                "session_type": display_session.get("session_type"),
                "display": display_session.get("display"),
                "wayland_display": display_session.get("wayland_display"),
                "warnings": wayland_warning,
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
