from __future__ import annotations

import gi

gi.require_version("Gdk", "4.0")
gi.require_version("Gtk", "4.0")
from gi.repository import Gdk, Gtk


CSS = b"""
window {
  background: #efe8db;
}
.hero {
  background: #fffaf0;
  border-radius: 22px;
  padding: 20px 22px;
}
.hero-title {
  font-size: 22px;
  font-weight: 800;
  color: #1d4039;
}
.hero-copy {
  color: #625d55;
}
.status-strip {
  background: #dfe9e3;
  border-radius: 18px;
  padding: 10px 12px;
}
.badge {
  background: #dbe8e1;
  color: #18473f;
  border-radius: 999px;
  padding: 6px 12px;
  font-weight: 700;
}
.badge-warning {
  background: #f5dfb8;
  color: #7a4c06;
}
.badge-blocked {
  background: #f0c8c3;
  color: #7e2e24;
}
.card {
  background: #fffaf0;
  border-radius: 20px;
  padding: 18px;
}
.card-title {
  font-size: 15px;
  font-weight: 800;
  color: #24211d;
}
.meta {
  color: #6a655d;
}
.accent-button {
  background: #c66f21;
  color: #fff8ef;
  border-radius: 14px;
  padding: 10px 16px;
  font-weight: 700;
}
.subtle-button {
  background: #e7ded1;
  color: #302c29;
  border-radius: 14px;
  padding: 10px 14px;
}
.chat-row {
  background: transparent;
  border-radius: 14px;
  padding: 10px 12px;
}
.chat-row-active {
  background: #eef3f0;
}
.chat-title {
  font-weight: 700;
  color: #24211d;
}
.chat-subtitle {
  color: #6b645c;
  font-size: 12px;
}
.dim-box {
  background: #f6efe1;
  border-radius: 16px;
  padding: 10px 12px;
}
.status-row {
  background: #fff7ea;
  border-radius: 14px;
  padding: 8px 10px;
}
"""


def install_css() -> None:
    provider = Gtk.CssProvider()
    provider.load_from_data(CSS)
    display = Gdk.Display.get_default()
    if display is not None:
        Gtk.StyleContext.add_provider_for_display(display, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
