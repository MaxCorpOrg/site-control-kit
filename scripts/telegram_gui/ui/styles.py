from __future__ import annotations

import os

from ..gtk_compat import Gdk, Gtk


UI_SCALE_ENV = "TELEGRAM_GUI_SCALE"
MIN_UI_SCALE = 0.75
MAX_UI_SCALE = 1.75


def resolve_ui_scale() -> float:
    raw = str(os.getenv(UI_SCALE_ENV, "1") or "1").strip()
    try:
        value = float(raw)
    except ValueError:
        value = 1.0
    return min(max(value, MIN_UI_SCALE), MAX_UI_SCALE)


def _px(value: int, scale: float) -> int:
    return max(1, int(round(value * scale)))


def build_css(scale: float | None = None) -> bytes:
    ui_scale = resolve_ui_scale() if scale is None else min(max(float(scale), MIN_UI_SCALE), MAX_UI_SCALE)
    return f"""
window {{
  background: #172634;
}}
* {{
  font-size: {_px(14, ui_scale)}px;
  font-family: "IBM Plex Mono", "PT Mono", "Noto Sans Mono", monospace;
  color: #d7e2ea;
}}
.hero {{
  background: linear-gradient(135deg, #1e2e3d, #172634);
  border-radius: {_px(2, ui_scale)}px;
  padding: {_px(22, ui_scale)}px {_px(24, ui_scale)}px;
  border: 1px solid #405364;
}}
.hero-text {{
  padding: {_px(4, ui_scale)}px {_px(4, ui_scale)}px;
}}
.hero-art {{
  background: #172634;
  border-radius: {_px(2, ui_scale)}px;
  border: 1px solid #405364;
  padding: {_px(8, ui_scale)}px;
}}
.hero-title {{
  font-family: "Press Start 2P", "IBM Plex Mono", "PT Mono", monospace;
  font-size: {_px(24, ui_scale)}px;
  font-weight: 800;
  color: #55f373;
  letter-spacing: {_px(1, ui_scale)}px;
}}
.hero-copy {{
  color: #9fafbc;
}}
.next-step {{
  background: #263847;
  color: #d7e2ea;
  border: 1px solid #55f373;
  border-left: {_px(4, ui_scale)}px solid #55f373;
  border-radius: {_px(2, ui_scale)}px;
  padding: {_px(10, ui_scale)}px {_px(14, ui_scale)}px;
  font-weight: 800;
}}
.status-strip {{
  background: #1e2e3d;
  border-radius: {_px(2, ui_scale)}px;
  padding: {_px(10, ui_scale)}px {_px(12, ui_scale)}px;
  border: 1px solid #405364;
}}
.badge {{
  background: #263847;
  color: #55f373;
  border: 1px solid #405364;
  border-radius: {_px(2, ui_scale)}px;
  padding: {_px(6, ui_scale)}px {_px(12, ui_scale)}px;
  font-weight: 700;
}}
.badge-warning {{
  background: rgba(240, 184, 75, 0.18);
  color: #f0b84b;
  border-color: #f0b84b;
}}
.badge-blocked {{
  background: rgba(239, 108, 117, 0.18);
  color: #ef6c75;
  border-color: #ef6c75;
}}
.card {{
  background: #1e2e3d;
  border-radius: {_px(2, ui_scale)}px;
  padding: {_px(18, ui_scale)}px;
  border: 1px solid #405364;
}}
.card-title {{
  font-family: "IBM Plex Mono", "PT Mono", "Noto Sans Mono", monospace;
  font-size: {_px(16, ui_scale)}px;
  font-weight: 800;
  color: #d7e2ea;
}}
.meta {{
  color: #9fafbc;
}}
.operator-note {{
  background: #263847;
  color: #d7e2ea;
  border: 1px solid #405364;
  border-left: {_px(4, ui_scale)}px solid #6ea7f8;
  border-radius: {_px(2, ui_scale)}px;
  padding: {_px(10, ui_scale)}px {_px(12, ui_scale)}px;
}}
button {{
  border: 1px solid #405364;
  box-shadow: none;
  background: #263847;
  color: #d7e2ea;
}}
button.accent-button, .accent-button {{
  background: #55f373;
  color: #07131d;
  border-color: #55f373;
  border-radius: {_px(2, ui_scale)}px;
  padding: {_px(12, ui_scale)}px {_px(18, ui_scale)}px;
  font-weight: 800;
  min-height: {_px(42, ui_scale)}px;
}}
button.accent-button label,
.accent-button label,
button.accent-button *,
.accent-button * {{
  color: #07131d;
}}
button.accent-button:hover, .accent-button:hover {{
  background: #7dff94;
  color: #07131d;
  border-color: #d7e2ea;
  box-shadow: 0 0 {_px(0, ui_scale)}px {_px(2, ui_scale)}px rgba(85, 243, 115, 0.42);
}}
button.accent-button:hover label, .accent-button:hover label {{
  color: #07131d;
}}
button.accent-button:active, .accent-button:active {{
  background: #2bdc55;
  color: #07131d;
  border-color: #55f373;
}}
button.subtle-button, .subtle-button {{
  background: #263847;
  color: #d7e2ea;
  border-color: #405364;
  border-radius: {_px(2, ui_scale)}px;
  padding: {_px(10, ui_scale)}px {_px(14, ui_scale)}px;
  min-height: {_px(38, ui_scale)}px;
}}
button.subtle-button:hover, .subtle-button:hover {{
  background: #55f373;
  color: #07131d;
  border-color: #55f373;
  box-shadow: 0 0 {_px(0, ui_scale)}px {_px(2, ui_scale)}px rgba(85, 243, 115, 0.42);
}}
button.subtle-button:hover label, .subtle-button:hover label {{
  color: #07131d;
}}
button.subtle-button:active, .subtle-button:active {{
  background: #172634;
  color: #55f373;
  border-color: #55f373;
}}
button.danger-button, .danger-button {{
  background: rgba(239, 108, 117, 0.16);
  color: #ef6c75;
  border-color: #ef6c75;
  border-radius: {_px(2, ui_scale)}px;
  padding: {_px(10, ui_scale)}px {_px(14, ui_scale)}px;
  font-weight: 800;
  min-height: {_px(38, ui_scale)}px;
}}
button.danger-button:hover, .danger-button:hover {{
  background: #ef6c75;
  color: #172634;
  border-color: #d7e2ea;
}}
button.danger-button:hover label, .danger-button:hover label {{
  color: #172634;
}}
button.danger-button:active, .danger-button:active {{
  background: #b8404c;
  color: #fff;
}}
button:disabled {{
  background: #1b2a37;
  color: #607382;
  border-color: #2d4050;
  opacity: 0.72;
}}
button:focus {{
  border-color: #6ea7f8;
  box-shadow: inset 0 0 0 {_px(1, ui_scale)}px #6ea7f8;
}}
button.button-hover, .button-hover {{
  background: #55f373;
  color: #07131d;
  border-color: #d7e2ea;
  box-shadow: 0 0 {_px(0, ui_scale)}px {_px(2, ui_scale)}px rgba(85, 243, 115, 0.50);
}}
button.button-hover label, .button-hover label {{
  color: #07131d;
}}
button.button-active, .button-active {{
  background: #2bdc55;
  color: #07131d;
  border-color: #55f373;
  box-shadow: inset 0 0 0 {_px(2, ui_scale)}px #55f373;
}}
button.button-active label, .button-active label {{
  color: #07131d;
}}
button.accent-button.button-active,
button.accent-button.button-active:active,
button.subtle-button.button-active,
button.subtle-button.button-active:active,
button.danger-button.button-active,
button.danger-button.button-active:active {{
  background: #2bdc55;
  color: #07131d;
  border-color: #55f373;
  box-shadow: inset 0 0 0 {_px(2, ui_scale)}px #172634;
}}
button.accent-button.button-active label,
button.subtle-button.button-active label,
button.danger-button.button-active label,
button.accent-button.button-active *,
button.subtle-button.button-active *,
button.danger-button.button-active * {{
  color: #07131d;
}}
.chat-row {{
  background: transparent;
  border-radius: {_px(2, ui_scale)}px;
  padding: {_px(10, ui_scale)}px {_px(12, ui_scale)}px;
}}
.chat-row:hover {{
  background: #263847;
}}
.chat-row-active {{
  background: #263847;
  border-left: {_px(4, ui_scale)}px solid #55f373;
}}
.chat-title {{
  font-weight: 700;
  color: #d7e2ea;
}}
.chat-subtitle {{
  color: #9fafbc;
  font-size: {_px(12, ui_scale)}px;
}}
.dim-box {{
  background: #263847;
  border-radius: {_px(2, ui_scale)}px;
  padding: {_px(10, ui_scale)}px {_px(12, ui_scale)}px;
  border: 1px solid #405364;
}}
.status-row {{
  background: #263847;
  border-radius: {_px(2, ui_scale)}px;
  padding: {_px(8, ui_scale)}px {_px(10, ui_scale)}px;
  border: 1px solid #405364;
}}
entry,
searchentry,
combobox,
combobox button,
combobox button.combo,
combobox box,
combobox cellview,
dropdown,
dropdown button,
textview,
textview text,
list,
listbox,
listview,
scrolledwindow,
scrolledwindow viewport,
viewport {{
  background: #172634;
  color: #d7e2ea;
  border: 1px solid #405364;
  border-radius: {_px(2, ui_scale)}px;
}}
entry *,
searchentry *,
combobox *,
dropdown *,
textview *,
list *,
listbox *,
listview * {{
  color: #d7e2ea;
}}
entry:focus,
searchentry:focus,
combobox button:focus,
dropdown button:focus {{
  border-color: #55f373;
  box-shadow: inset 0 0 0 {_px(1, ui_scale)}px #55f373;
}}
combobox arrow,
dropdown arrow {{
  color: #d7e2ea;
}}
combobox button:hover,
dropdown button:hover {{
  background: #263847;
  border-color: #55f373;
}}
combobox button:hover *,
dropdown button:hover * {{
  color: #d7e2ea;
}}
popover,
popover contents,
popover list,
popover listview,
popover row {{
  background: #172634;
  color: #d7e2ea;
  border-color: #405364;
}}
popover row:hover,
popover row:selected {{
  background: #263847;
  color: #55f373;
}}
popover row:hover *,
popover row:selected * {{
  color: #55f373;
}}
listbox row,
list row,
listview row {{
  background: #172634;
  color: #d7e2ea;
}}
listbox row:hover,
list row:hover,
listview row:hover {{
  background: #263847;
}}
listbox row:selected,
list row:selected,
listview row:selected {{
  background: #263847;
  color: #55f373;
}}
stackswitcher button {{
  background: #263847;
  color: #d7e2ea;
  border: 1px solid #405364;
  border-radius: {_px(2, ui_scale)}px;
}}
stackswitcher button label,
stackswitcher button * {{
  color: #d7e2ea;
}}
stackswitcher button:hover {{
  background: #55f373;
  color: #07131d;
  border-color: #55f373;
}}
stackswitcher button:hover label,
stackswitcher button:hover * {{
  color: #07131d;
}}
stackswitcher button:checked,
stackswitcher button:active {{
  background: #55f373;
  color: #07131d;
  border-color: #55f373;
}}
stackswitcher button:checked label,
stackswitcher button:checked *,
stackswitcher button:active label,
stackswitcher button:active * {{
  color: #07131d;
}}
progressbar trough {{
  min-height: {_px(14, ui_scale)}px;
  border-radius: {_px(2, ui_scale)}px;
  background: #263847;
  border: 1px solid #405364;
}}
progressbar progress {{
  min-height: {_px(14, ui_scale)}px;
  border-radius: {_px(2, ui_scale)}px;
  background: #55f373;
}}
""".encode("utf-8")


def install_css() -> None:
    provider = Gtk.CssProvider()
    provider.load_from_data(build_css())
    display = Gdk.Display.get_default()
    if display is not None:
        Gtk.StyleContext.add_provider_for_display(display, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)


def attach_button_feedback(button: object) -> None:
    """Make button hover/press feedback explicit across GTK themes."""
    try:
        motion = Gtk.EventControllerMotion.new()
        motion.connect("enter", lambda *_args: button.add_css_class("button-hover"))
        motion.connect("leave", lambda *_args: button.remove_css_class("button-hover"))
        button.add_controller(motion)
    except Exception:
        return
    try:
        click = Gtk.GestureClick.new()
        click.connect("pressed", lambda *_args: button.add_css_class("button-active"))
        click.connect("released", lambda *_args: button.remove_css_class("button-active"))
        click.connect("cancel", lambda *_args: button.remove_css_class("button-active"))
        button.add_controller(click)
    except Exception:
        pass
