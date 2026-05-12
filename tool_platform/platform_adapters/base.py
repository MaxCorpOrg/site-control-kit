from __future__ import annotations

import importlib.util
import os
import shutil
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class PlatformAdapter:
    platform_id: str
    display_name: str

    def _command_available(self, command: str) -> bool:
        return shutil.which(command) is not None

    def _module_available(self, module_name: str) -> bool:
        return importlib.util.find_spec(module_name) is not None

    def capabilities(self) -> dict[str, Any]:
        raise NotImplementedError

    def doctor(self) -> dict[str, Any]:
        capabilities = self.capabilities()
        available = [name for name, value in capabilities.items() if bool(value.get("available"))]
        missing = [name for name, value in capabilities.items() if not bool(value.get("available"))]
        return {
            "platform_id": self.platform_id,
            "display_name": self.display_name,
            "capabilities": capabilities,
            "available_capabilities": available,
            "missing_capabilities": missing,
        }

    def launch_app(self, *_args: Any, **_kwargs: Any) -> dict[str, Any]:
        raise NotImplementedError(f"{self.display_name} adapter does not implement launch_app yet")

    def open_uri(self, *_args: Any, **_kwargs: Any) -> dict[str, Any]:
        raise NotImplementedError(f"{self.display_name} adapter does not implement open_uri yet")

    def find_window(self, *_args: Any, **_kwargs: Any) -> dict[str, Any]:
        raise NotImplementedError(f"{self.display_name} adapter does not implement find_window yet")

    def focus_window(self, *_args: Any, **_kwargs: Any) -> dict[str, Any]:
        raise NotImplementedError(f"{self.display_name} adapter does not implement focus_window yet")

    def click_relative(self, *_args: Any, **_kwargs: Any) -> dict[str, Any]:
        raise NotImplementedError(f"{self.display_name} adapter does not implement click_relative yet")

    def send_keys(self, *_args: Any, **_kwargs: Any) -> dict[str, Any]:
        raise NotImplementedError(f"{self.display_name} adapter does not implement send_keys yet")

    def capture_screenshot(self, *_args: Any, **_kwargs: Any) -> dict[str, Any]:
        raise NotImplementedError(f"{self.display_name} adapter does not implement capture_screenshot yet")

    def inspect_accessibility(self, *_args: Any, **_kwargs: Any) -> dict[str, Any]:
        raise NotImplementedError(
            f"{self.display_name} adapter does not implement inspect_accessibility yet"
        )


def gui_capability() -> dict[str, Any]:
    return {
        "available": importlib.util.find_spec("tkinter") is not None,
        "detail": "tkinter",
    }


def display_session_snapshot() -> dict[str, Any]:
    return {
        "session_type": str(os.environ.get("XDG_SESSION_TYPE") or "").strip().lower() or "unknown",
        "display": str(os.environ.get("DISPLAY") or "").strip(),
        "wayland_display": str(os.environ.get("WAYLAND_DISPLAY") or "").strip(),
    }


def home_display_capability() -> dict[str, Any]:
    session = display_session_snapshot()
    return {
        "available": bool(session["display"] or session["wayland_display"]),
        "detail": "DISPLAY/WAYLAND_DISPLAY",
        "session_type": session["session_type"],
        "display": session["display"],
        "wayland_display": session["wayland_display"],
        "warnings": ["Wayland detected"] if session["session_type"] == "wayland" else [],
    }


def capability_warnings(capabilities: dict[str, Any]) -> list[str]:
    warnings: list[str] = []
    for value in capabilities.values():
        if not isinstance(value, dict):
            continue
        raw_items = value.get("warnings")
        if not isinstance(raw_items, list):
            continue
        for item in raw_items:
            text = str(item or "").strip()
            if text and text not in warnings:
                warnings.append(text)
    return warnings
