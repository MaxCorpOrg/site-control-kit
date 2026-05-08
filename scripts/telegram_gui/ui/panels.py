from __future__ import annotations

from pathlib import Path
from typing import Callable

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk

from ..models import ArtifactBundle, PreflightInfo, PreflightStatus, RunRecord, SessionResumeState


class ProgressPanel(Gtk.Box):
    def __init__(self) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.set_vexpand(True)

        summary = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        summary.add_css_class("dim-box")
        self.append(summary)

        self.summary_label = Gtk.Label(label="Запуск ещё не начат")
        self.summary_label.set_xalign(0)
        self.summary_label.set_wrap(True)
        self.summary_label.add_css_class("card-title")
        self.summary_meta_label = Gtk.Label(label="Сообщений: 0 | @username: 0")
        self.summary_meta_label.set_xalign(0)
        self.summary_meta_label.set_wrap(True)
        self.summary_meta_label.add_css_class("meta")
        summary.append(self.summary_label)
        summary.append(self.summary_meta_label)

        self.progress_bar = Gtk.ProgressBar()
        self.progress_bar.set_show_text(True)
        self.progress_bar.set_text("Ожидание")
        self.progress_bar.set_fraction(0.0)
        self.progress_status_label = Gtk.Label(label="Прогресс появится после старта экспорта")
        self.progress_meta_label = Gtk.Label(label="Сообщений: 0 | @username: 0")
        self.progress_hint_label = Gtk.Label(
            label="Долгие чаты сканируются по истории. Кнопка остановки активируется во время сбора."
        )
        for widget in (self.progress_status_label, self.progress_meta_label, self.progress_hint_label):
            widget.set_xalign(0)
            widget.set_wrap(True)
        self.append(self.progress_bar)
        self.append(self.progress_status_label)
        self.append(self.progress_meta_label)
        self.append(self.progress_hint_label)

        log_title = Gtk.Label(label="Live log")
        log_title.set_xalign(0)
        self.append(log_title)

        self.log_buffer = Gtk.TextBuffer()
        self.log_view = Gtk.TextView(buffer=self.log_buffer)
        self.log_view.set_editable(False)
        self.log_view.set_cursor_visible(False)
        self.log_view.set_monospace(True)
        self.log_view.set_vexpand(True)
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scroll.set_vexpand(True)
        scroll.set_child(self.log_view)
        self.append(scroll)

    def set_summary(self, text: str, meta: str) -> None:
        self.summary_label.set_label(text)
        self.summary_meta_label.set_label(meta)


class PreflightPanel(Gtk.Box):
    def __init__(self) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.set_vexpand(False)

        header = Gtk.Label(label="Preflight checklist")
        header.set_xalign(0)
        header.add_css_class("card-title")
        self.append(header)

        self.summary_label = Gtk.Label(label="Preflight появится после выбора профиля")
        self.summary_label.set_xalign(0)
        self.summary_label.set_wrap(True)
        self.summary_label.add_css_class("meta")
        self.append(self.summary_label)

        self.rows_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.append(self.rows_box)

    def set_info(self, info: PreflightInfo) -> None:
        summary_lines = [
            f"Surface: {info.surface_label}",
            f"Preset: {info.preset_label}",
            f"Security: {info.security_mode or '—'}",
        ]
        if info.notes:
            summary_lines.append(" / ".join(info.notes[:2]))
        self.summary_label.set_label("\n".join(summary_lines))
        while True:
            child = self.rows_box.get_first_child()
            if child is None:
                break
            self.rows_box.remove(child)
        for status in info.statuses:
            self.rows_box.append(_status_row(status))


def _status_row(status: PreflightStatus) -> Gtk.Widget:
    row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    row.add_css_class("status-row")
    badge = Gtk.Label(label=status.state.upper())
    badge.add_css_class("badge")
    if status.state == "warning":
        badge.add_css_class("badge-warning")
    elif status.state == "blocked":
        badge.add_css_class("badge-blocked")
    text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
    title = Gtk.Label(label=status.label)
    title.set_xalign(0)
    title.add_css_class("card-title")
    detail = Gtk.Label(label=status.detail)
    detail.set_xalign(0)
    detail.set_wrap(True)
    detail.add_css_class("meta")
    text.append(title)
    text.append(detail)
    row.append(badge)
    row.append(text)
    return row


class ArtifactPanel(Gtk.Box):
    def __init__(
        self,
        open_path: Callable[[Path], None],
        open_parent: Callable[[Path], None],
        copy_path: Callable[[Path], None],
    ) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.set_vexpand(True)
        self._open_path = open_path
        self._open_parent = open_parent
        self._copy_path = copy_path
        self.summary_label = Gtk.Label(label="Артефакты текущего запуска появятся здесь")
        self.summary_label.set_xalign(0)
        self.summary_label.set_wrap(True)
        self.append(self.summary_label)

        self.button_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.append(self.button_box)

    def set_artifacts(self, bundle: ArtifactBundle | None, *, summary: str) -> None:
        self.summary_label.set_label(summary)
        while True:
            child = self.button_box.get_first_child()
            if child is None:
                break
            self.button_box.remove(child)
        if bundle is None:
            return
        for label, path in bundle.entries():
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            name = Gtk.Label(label=f"{label}: {path.name}")
            name.set_xalign(0)
            name.set_hexpand(True)
            name.set_wrap(True)
            row.append(name)
            open_button = Gtk.Button(label="Открыть")
            open_button.connect("clicked", lambda _btn, p=path: self._open_path(p))
            folder_button = Gtk.Button(label="Папка")
            folder_button.connect("clicked", lambda _btn, p=path: self._open_parent(p))
            copy_button = Gtk.Button(label="Копировать путь")
            copy_button.connect("clicked", lambda _btn, p=path: self._copy_path(p))
            for button in (open_button, folder_button, copy_button):
                button.add_css_class("subtle-button")
                row.append(button)
            self.button_box.append(row)


class HistoryPanel(Gtk.Box):
    def __init__(self) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.set_vexpand(True)
        self.resume_label = Gtk.Label(label="Resume Last недоступен")
        self.resume_label.set_xalign(0)
        self.resume_label.set_wrap(True)
        self.append(self.resume_label)

        self.filter_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.append(self.filter_box)
        self._filter_buttons: dict[str, Gtk.Button] = {}
        self.active_filter = "all"
        for key, label in (
            ("all", "Все"),
            ("primary", "Primary"),
            ("fallback", "Fallback"),
            ("partial", "Partial"),
            ("done", "Done"),
        ):
            button = Gtk.Button(label=label)
            button.add_css_class("subtle-button")
            self._filter_buttons[key] = button
            self.filter_box.append(button)

        self.listbox = Gtk.ListBox()
        self.listbox.set_selection_mode(Gtk.SelectionMode.SINGLE)
        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_child(self.listbox)
        self.append(scroll)
        self._runs: list[RunRecord] = []

    def bind_filter(self, callback: Callable[[str], None]) -> None:
        for key, button in self._filter_buttons.items():
            button.connect("clicked", lambda _btn, selected=key: callback(selected))

    def set_active_filter(self, key: str) -> None:
        self.active_filter = key

    def set_resume_state(self, session: SessionResumeState | None) -> None:
        if session is None:
            self.resume_label.set_label("Resume Last недоступен")
            return
        self.resume_label.set_label(
            f"Resume Last: {session.chat_title or session.chat_ref} -> {session.output_path} ({session.surface_badge})"
        )

    def set_runs(self, runs: list[RunRecord], *, filter_key: str = "all") -> None:
        self._runs = runs
        filtered = [run for run in runs if _run_matches_filter(run, filter_key)]
        while True:
            child = self.listbox.get_first_child()
            if child is None:
                break
            self.listbox.remove(child)
        for run in filtered:
            row = Gtk.ListBoxRow()
            row.run_record = run  # type: ignore[attr-defined]
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            title = Gtk.Label(
                label=f"{run.chat_title or run.chat_ref} | {run.preset_label} | {run.surface_badge}",
            )
            title.set_xalign(0)
            title.set_wrap(True)
            summary = run.summary()
            meta = Gtk.Label(
                label=(
                    f"{run.created_at} | status={summary.status or 'done'} | @{run.usernames_found} | "
                    f"safe {run.safe_count} | {summary.duration_sec}s"
                ),
            )
            meta.set_xalign(0)
            meta.set_wrap(True)
            meta.add_css_class("meta")
            box.append(title)
            box.append(meta)
            row.set_child(box)
            self.listbox.append(row)


def _run_matches_filter(run: RunRecord, key: str) -> bool:
    summary = run.summary()
    if key == "all":
        return True
    if key == "primary":
        return run.surface_key == "tdata"
    if key == "fallback":
        return run.surface_key in {"bridge", "cdp"}
    if key == "partial":
        return summary.status == "partial" or run.interrupted
    if key == "done":
        return summary.status == "done" and not run.interrupted
    return True
