from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Callable


def _noop(*_args: Any, **_kwargs: Any) -> None:
    return None


class _DummyMeta(type):
    def __getattr__(cls, name: str) -> Any:
        if not name:
            raise AttributeError(name)
        if name[0].isupper():
            nested = _make_dummy_class(f"{cls.__name__}.{name}")
            setattr(cls, name, nested)
            return nested
        return _noop


class _DummyObject(metaclass=_DummyMeta):
    def __init__(self, *_args: Any, **_kwargs: Any) -> None:
        pass

    def __getattr__(self, _name: str) -> Callable[..., Any]:
        return _noop


def _make_dummy_class(name: str) -> type[_DummyObject]:
    return _DummyMeta(name, (_DummyObject,), {})


class _DummyModule(SimpleNamespace):
    def __getattr__(self, name: str) -> Any:
        if not name:
            raise AttributeError(name)
        if name == "idle_add":
            return lambda func, *args, **kwargs: func(*args, **kwargs) if callable(func) else None
        if name == "timeout_add":
            return lambda _ms, func, *args, **kwargs: func(*args, **kwargs) if callable(func) else None
        if name[0].isupper():
            value = _make_dummy_class(name)
        else:
            value = _noop
        setattr(self, name, value)
        return value


def _load_real_gtk() -> tuple[bool, Any, Any, Any, Any, Any]:
    import gi

    gi.require_version("Gdk", "4.0")
    gi.require_version("Gtk", "4.0")
    from gi.repository import Gdk, Gio, GLib, Gtk, Pango

    return True, Gdk, Gio, GLib, Gtk, Pango


try:  # pragma: no cover - exercised in environments with GTK available
    GTK_AVAILABLE, Gdk, Gio, GLib, Gtk, Pango = _load_real_gtk()
except Exception:  # pragma: no cover - exercised in Windows/no-GTK test environments
    GTK_AVAILABLE = False
    Gdk = _DummyModule()
    Gio = _DummyModule()
    GLib = _DummyModule()
    Gtk = _DummyModule(STYLE_PROVIDER_PRIORITY_APPLICATION=0)
    Pango = _DummyModule()


__all__ = ["GTK_AVAILABLE", "Gdk", "Gio", "GLib", "Gtk", "Pango"]
