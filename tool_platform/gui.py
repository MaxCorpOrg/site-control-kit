from __future__ import annotations

import argparse
import json
import logging
import queue
import re
import shlex
import subprocess
import tempfile
import threading
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

try:
    import tkinter as tk
    from tkinter import filedialog, font as tkfont, messagebox, ttk
except ModuleNotFoundError as exc:  # pragma: no cover - depends on system packages
    tk = None
    filedialog = None
    tkfont = None
    messagebox = None
    ttk = None
    TKINTER_IMPORT_ERROR = exc
else:  # pragma: no cover - trivial branch
    TKINTER_IMPORT_ERROR = None

from .catalog import DEFAULT_REGISTRY_PATH, ToolManifest, load_catalog
from .telegram_gui_helpers import (
    CommandSpec,
    DEFAULT_INVITE_OUTPUT_ROOT,
    DEFAULT_SESSION_CONFIG,
    build_session_runtime_config,
    default_invite_job_dir,
    format_session_target_label,
    invite_manager_init_command,
    invite_manager_next_command,
    invite_manager_status_command,
    parse_json_payload,
    session_message_targets,
    session_plan_command,
    session_run_command,
)
from .telegram_profiles import (
    DEFAULT_OUTPUT_ROOT,
    adopt_existing_profile,
    format_profile_label,
    get_profile_status,
    import_tdata_profile,
    launch_profile,
    list_portable_profiles,
)


USERNAME_RE = re.compile(r"^@?[A-Za-z0-9_]{5,32}$")
PANEL_LOG_PATH = Path("/tmp/telegram-control-center-panel.log")
LOGGER = logging.getLogger("telegram_control_center_panel")
if not LOGGER.handlers:
    PANEL_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    _handler = logging.FileHandler(PANEL_LOG_PATH, encoding="utf-8")
    _handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    LOGGER.addHandler(_handler)
LOGGER.setLevel(logging.INFO)
LOGGER.propagate = False


def format_profile_details(profile: dict[str, Any]) -> str:
    account = profile.get("account") if isinstance(profile.get("account"), dict) else {}
    windows = profile.get("windows") if isinstance(profile.get("windows"), list) else []
    first_window = windows[0] if windows else {}
    running_text = "Запущен" if profile.get("running") else "Остановлен"
    lines = [
        "Профиль Telegram",
        f"Имя профиля: {profile.get('profile_name') or 'неизвестно'}",
        f"Username аккаунта: {account.get('username') or 'не задан'}",
        f"Метка аккаунта: {account.get('label') or 'не задана'}",
        f"Состояние: {running_text}",
        f"Количество PID: {len(profile.get('pids') or [])}",
        "",
        "Пути",
        f"Папка профиля: {profile.get('profile_dir') or '-'}",
        f"Папка tdata: {profile.get('tdata_dir') or '-'}",
        f"Metadata: {profile.get('metadata_path') or '-'}",
        f"Telegram log: {profile.get('telegram_log_path') or '-'}",
        "",
        "Окно",
        f"Заголовок окна: {first_window.get('title') or 'недоступно'}",
        f"ID окна: {first_window.get('window_id') or 'недоступно'}",
    ]
    return "\n".join(lines)


def format_workflow_details(tool: ToolManifest) -> str:
    lines = [
        "Инструмент Telegram",
        f"Название: {tool.display_name}",
        f"Tool ID: {tool.tool_id}",
        f"Тип: {tool.kind}",
        f"Источник: {tool.source_label}",
        f"Standalone: {'да' if tool.standalone else 'нет'}",
        f"Рабочая папка: {tool.root_dir}",
        f"Manifest: {tool.manifest_path}",
    ]
    if tool.description:
        lines.extend(["", "Описание", tool.description])
    if tool.capabilities:
        lines.extend(["", "Возможности", *[f"- {item}" for item in tool.capabilities]])
    if tool.tags:
        lines.extend(["", "Теги", *[f"- {item}" for item in tool.tags]])
    if tool.docs:
        lines.extend(["", "Документы", *[f"- {doc.label}: {doc.path}" for doc in tool.docs]])
    if tool.artifacts:
        lines.extend(
            ["", "Артефакты", *[f"- {key}: {value}" for key, value in tool.artifacts.items()]]
        )
    return "\n".join(lines)


def format_invite_status_payload(payload: dict[str, Any]) -> str:
    counts = payload.get("counts") if isinstance(payload.get("counts"), dict) else {}
    next_users = payload.get("users") if isinstance(payload.get("users"), list) else []
    latest_runs = payload.get("latest_runs") if isinstance(payload.get("latest_runs"), list) else []

    lines = [
        "Инвайты по списку",
        f"Папка задачи: {payload.get('job_dir') or '-'}",
        f"Чат: {payload.get('chat_url') or '-'}",
        f"Всего пользователей: {payload.get('total_users') or 0}",
        f"С consent=yes: {payload.get('consent_yes') or 0}",
        f"С consent=no: {payload.get('consent_no') or 0}",
        "",
        "Статусы",
    ]
    if counts:
        for key, value in sorted(counts.items()):
            lines.append(f"- {key}: {value}")
    if next_users:
        lines.extend(["", "Следующие пользователи"])
        for item in next_users:
            lines.append(
                f"- {item.get('username') or '-'} · статус: {item.get('status') or '-'} · попыток: {item.get('attempts') or 0}"
            )
    if latest_runs:
        lines.extend(["", "Последние прогоны"])
        for run in latest_runs:
            lines.append(
                f"- {run.get('run_id') or '-'} · processed={run.get('processed') or 0} · updated={run.get('updated') or 0} · dry_run={int(bool(run.get('dry_run')))}"
            )
    return "\n".join(lines)


def format_session_plan_payload(payload: dict[str, Any]) -> str:
    plan = payload.get("plan") if isinstance(payload.get("plan"), dict) else payload
    visits = plan.get("visits") if isinstance(plan.get("visits"), list) else []
    drafts = plan.get("message_drafts") if isinstance(plan.get("message_drafts"), list) else []
    lines = [
        "Сессия и сообщения",
        f"Визитов в плане: {len(visits)}",
        f"Черновиков сообщений: {len(drafts)}",
        f"Текущий адресат сообщений: {plan.get('message_target_username') or 'не выбран'}",
    ]
    if visits:
        lines.extend(["", "Первые визиты"])
        for item in visits[:8]:
            lines.append(
                f"- {item.get('label') or item.get('target_id') or '-'} · {item.get('kind') or '-'} · {item.get('view_seconds') or 0} сек"
            )
    if drafts:
        lines.extend(["", "Шаблоны сообщений"])
        for item in drafts:
            lines.append(f"- {item.get('text') or ''}")
    return "\n".join(lines)


def format_session_run_payload(payload: dict[str, Any]) -> str:
    run_info = payload.get("run") if isinstance(payload.get("run"), dict) else payload
    visits = run_info.get("visits") if isinstance(run_info.get("visits"), list) else []
    drafts = run_info.get("message_drafts") if isinstance(run_info.get("message_drafts"), list) else []
    lines = [
        "Сессия и сообщения",
        f"Статус: {payload.get('status') or run_info.get('status') or 'ok'}",
        f"Запуск: {payload.get('run_dir') or run_info.get('run_dir') or '-'}",
        f"Выполнено визитов: {len(visits)}",
        f"Подготовлено сообщений: {len(drafts)}",
        f"Адресат сообщений: {run_info.get('message_target_username') or '-'}",
    ]
    history = payload.get("history") if isinstance(payload.get("history"), list) else []
    if history:
        lines.extend(["", "История"])
        for item in history[-5:]:
            lines.append(f"- {item}")
    return "\n".join(lines)


if tk is not None:

    class ToolPlatformPanel(tk.Tk):
        def __init__(self, registry_path: str) -> None:
            super().__init__()
            self.registry_path = registry_path
            self.catalog = load_catalog(registry_path)
            self.tools_by_id = {tool.tool_id: tool for tool in self.catalog.tools}
            for required_tool_id in ("telegram_invite_manager", "telegram_session_runner"):
                if required_tool_id not in self.tools_by_id:
                    raise RuntimeError(
                        f"В registry отсутствует обязательный инструмент: {required_tool_id}"
                    )
            self._colors = {
                "bg": "#f3efe7",
                "surface": "#fffaf2",
                "surface_alt": "#f7f1e7",
                "field": "#fffdf8",
                "border": "#d9cfbf",
                "text": "#182126",
                "muted": "#5f6b73",
                "accent": "#176b87",
                "accent_active": "#12546a",
                "accent_text": "#ffffff",
                "inactive_button": "#efe7d9",
            }
            self._fonts: dict[str, Any] = {}
            self._configure_styles()

            self.title("Центр управления Telegram")
            self.geometry("1460x980")
            self.minsize(1200, 780)

            self.summary_var = tk.StringVar()
            self.output_root_var = tk.StringVar(value=str(DEFAULT_OUTPUT_ROOT))
            self.profile_choice_var = tk.StringVar()
            self.import_zip_var = tk.StringVar()
            self.import_profile_name_var = tk.StringVar()
            self.import_account_username_var = tk.StringVar()
            self.import_account_label_var = tk.StringVar()
            self.adopt_profile_dir_var = tk.StringVar()
            self.adopt_profile_name_var = tk.StringVar()
            self.adopt_account_username_var = tk.StringVar()
            self.adopt_account_label_var = tk.StringVar()

            self.invite_chat_url_var = tk.StringVar()
            self.invite_input_path_var = tk.StringVar()
            self.invite_job_dir_var = tk.StringVar()
            self.invite_limit_var = tk.StringVar(value="10")

            self.session_config_path_var = tk.StringVar(value=str(DEFAULT_SESSION_CONFIG))
            self.session_new_target_var = tk.StringVar()
            self.session_new_target_label_var = tk.StringVar()
            self.session_new_target_kind_var = tk.StringVar(value="Контакт")
            self.session_auto_send_var = tk.BooleanVar(value=False)
            self.invite_status_var = tk.StringVar(value="Готово")
            self.session_status_var = tk.StringVar(value="Готово")

            self._profiles: list[dict[str, Any]] = []
            self._session_targets: list[dict[str, Any]] = []
            self._active_tool_id = "telegram_invite_manager"
            self._active_processes: dict[str, subprocess.Popen[str]] = {}
            self._busy_controls: dict[str, list[Any]] = {
                "telegram_invite_manager": [],
                "telegram_session_runner": [],
            }
            self._stop_controls: dict[str, list[Any]] = {
                "telegram_invite_manager": [],
                "telegram_session_runner": [],
            }
            self._process_lock = threading.Lock()
            self._ui_queue: queue.Queue[tuple[str, str, dict[str, Any] | None, str, bool, Callable[[dict[str, Any]], None]]] = queue.Queue()
            self._scroll_canvas: tk.Canvas | None = None

            self.profile_combo: ttk.Combobox | None = None
            self.profile_details: tk.Text | None = None
            self.profile_manager_window: tk.Toplevel | None = None
            self.invite_output: tk.Text | None = None
            self.session_output: tk.Text | None = None
            self.session_targets_list: tk.Listbox | None = None
            self._tool_buttons: dict[str, tk.Button] = {}
            self._tool_frames: dict[str, ttk.Frame] = {}

            self.invite_chat_url_var.trace_add("write", self._sync_invite_job_dir)

            self._build_ui()
            self._reload_profiles(initial=True)
            self._load_session_targets(show_feedback=False)
            self._switch_tool("telegram_invite_manager")
            self.after(120, self._drain_ui_queue)

        def _configure_styles(self) -> None:
            if ttk is None or tkfont is None:
                return
            style = ttk.Style(self)
            try:
                style.theme_use("clam")
            except tk.TclError:
                pass

            base_font = tkfont.nametofont("TkDefaultFont").copy()
            base_font.configure(size=11)
            label_font = base_font.copy()
            label_font.configure(weight="bold")
            section_font = base_font.copy()
            section_font.configure(size=12, weight="bold")
            hero_font = base_font.copy()
            hero_font.configure(size=20, weight="bold")
            small_font = base_font.copy()
            small_font.configure(size=10)
            self._fonts = {
                "base": base_font,
                "label": label_font,
                "section": section_font,
                "hero": hero_font,
                "small": small_font,
            }

            self.configure(bg=self._colors["bg"])
            style.configure(".", background=self._colors["bg"], foreground=self._colors["text"])
            style.configure("App.TFrame", background=self._colors["bg"])
            style.configure("Card.TFrame", background=self._colors["surface"])
            style.configure(
                "HeroTitle.TLabel",
                background=self._colors["bg"],
                foreground=self._colors["text"],
                font=self._fonts["hero"],
            )
            style.configure(
                "HeroSub.TLabel",
                background=self._colors["bg"],
                foreground=self._colors["muted"],
                font=self._fonts["small"],
            )
            style.configure(
                "CardTitle.TLabel",
                background=self._colors["surface"],
                foreground=self._colors["text"],
                font=self._fonts["section"],
            )
            style.configure(
                "CardSubtitle.TLabel",
                background=self._colors["surface"],
                foreground=self._colors["muted"],
                font=self._fonts["small"],
            )
            style.configure(
                "Field.TLabel",
                background=self._colors["surface"],
                foreground=self._colors["muted"],
                font=self._fonts["small"],
            )
            style.configure(
                "TEntry",
                fieldbackground=self._colors["field"],
                foreground=self._colors["text"],
                padding=(10, 8),
                bordercolor=self._colors["border"],
                lightcolor=self._colors["border"],
                darkcolor=self._colors["border"],
            )
            style.configure(
                "TCombobox",
                fieldbackground=self._colors["field"],
                foreground=self._colors["text"],
                padding=(8, 6),
                bordercolor=self._colors["border"],
                lightcolor=self._colors["border"],
                darkcolor=self._colors["border"],
                arrowsize=16,
            )
            style.map(
                "TCombobox",
                fieldbackground=[("readonly", self._colors["field"])],
                selectbackground=[("readonly", self._colors["field"])],
                selectforeground=[("readonly", self._colors["text"])],
            )
            style.configure(
                "TButton",
                font=self._fonts["base"],
                padding=(12, 8),
                background=self._colors["surface_alt"],
                foreground=self._colors["text"],
                bordercolor=self._colors["border"],
                lightcolor=self._colors["border"],
                darkcolor=self._colors["border"],
            )
            style.map("TButton", background=[("active", self._colors["field"])])
            style.configure(
                "Accent.TButton",
                font=self._fonts["label"],
                padding=(14, 9),
                background=self._colors["accent"],
                foreground=self._colors["accent_text"],
                bordercolor=self._colors["accent"],
                lightcolor=self._colors["accent"],
                darkcolor=self._colors["accent"],
            )
            style.map(
                "Accent.TButton",
                background=[("active", self._colors["accent_active"])],
                foreground=[("active", self._colors["accent_text"])],
            )

        def _create_readonly_text(self, parent: ttk.Frame, *, height: int) -> tk.Text:
            widget = tk.Text(
                parent,
                wrap="word",
                height=height,
                bg=self._colors["field"],
                fg=self._colors["text"],
                insertbackground=self._colors["text"],
                highlightbackground=self._colors["border"],
                highlightcolor=self._colors["accent"],
                highlightthickness=1,
                relief="flat",
                borderwidth=0,
                padx=14,
                pady=12,
                spacing1=2,
                spacing3=4,
                font=self._fonts["base"],
            )
            widget.configure(state="disabled", cursor="arrow")
            return widget

        def _set_readonly_text(self, widget: tk.Text | None, content: str) -> None:
            if widget is None:
                return
            widget.configure(state="normal")
            widget.delete("1.0", tk.END)
            widget.insert("1.0", content.strip() + "\n")
            widget.configure(state="disabled")

        def _append_readonly_text(self, widget: tk.Text | None, content: str) -> None:
            if widget is None:
                return
            widget.configure(state="normal")
            if widget.index("end-1c") != "1.0":
                widget.insert(tk.END, "\n")
            widget.insert(tk.END, content.rstrip() + "\n")
            widget.see(tk.END)
            widget.configure(state="disabled")

        def _status_var_for_tool(self, tool_id: str) -> tk.StringVar:
            return (
                self.invite_status_var
                if tool_id == "telegram_invite_manager"
                else self.session_status_var
            )

        def _output_widget_for_tool(self, tool_id: str) -> tk.Text | None:
            return self.invite_output if tool_id == "telegram_invite_manager" else self.session_output

        def _log_event(self, tool_id: str, message: str) -> None:
            line = f"[{datetime.now().strftime('%H:%M:%S')}] {message}"
            LOGGER.info("%s | %s", tool_id, message)
            self._append_readonly_text(self._output_widget_for_tool(tool_id), line)

        def _register_busy_widget(self, tool_id: str, widget: Any) -> None:
            self._busy_controls[tool_id].append(widget)

        def _register_stop_widget(self, tool_id: str, widget: Any) -> None:
            self._stop_controls[tool_id].append(widget)

        def _set_tool_busy(self, tool_id: str, busy: bool) -> None:
            state = "disabled" if busy else "normal"
            for widget in self._busy_controls[tool_id]:
                try:
                    widget.configure(state=state)
                except tk.TclError:
                    continue
            stop_state = "normal" if busy else "disabled"
            for widget in self._stop_controls[tool_id]:
                try:
                    widget.configure(state=stop_state)
                except tk.TclError:
                    continue

        def _create_listbox(self, parent: tk.Widget, *, selectmode: str = tk.SINGLE, height: int = 6) -> tk.Listbox:
            return tk.Listbox(
                parent,
                activestyle="none",
                bg=self._colors["field"],
                fg=self._colors["text"],
                selectbackground=self._colors["accent"],
                selectforeground=self._colors["accent_text"],
                highlightbackground=self._colors["border"],
                highlightcolor=self._colors["accent"],
                highlightthickness=1,
                borderwidth=0,
                relief="flat",
                font=self._fonts["base"],
                exportselection=False,
                selectmode=selectmode,
                height=height,
            )

        def _create_card(
            self,
            parent: ttk.Frame,
            title: str,
            subtitle: str,
            *,
            expand: bool = False,
        ) -> ttk.Frame:
            card = ttk.Frame(parent, style="Card.TFrame", padding=16)
            card.pack(fill="both", expand=expand, pady=(0, 14))
            ttk.Label(card, text=title, style="CardTitle.TLabel").pack(anchor="w")
            if subtitle:
                ttk.Label(card, text=subtitle, style="CardSubtitle.TLabel").pack(
                    anchor="w", pady=(4, 12)
                )
            body = ttk.Frame(card, style="Card.TFrame")
            body.pack(fill="both", expand=True)
            return body

        def _create_inline_panel(self, parent: tk.Widget, title: str, subtitle: str) -> tk.Frame:
            panel = tk.Frame(
                parent,
                bg=self._colors["field"],
                highlightbackground=self._colors["border"],
                highlightcolor=self._colors["border"],
                highlightthickness=1,
                bd=0,
                padx=12,
                pady=12,
            )
            tk.Label(
                panel,
                text=title,
                bg=self._colors["field"],
                fg=self._colors["text"],
                font=self._fonts["label"],
                anchor="w",
            ).grid(row=0, column=0, sticky="w")
            tk.Label(
                panel,
                text=subtitle,
                bg=self._colors["field"],
                fg=self._colors["muted"],
                font=self._fonts["small"],
                justify="left",
                anchor="w",
            ).grid(row=1, column=0, sticky="w", pady=(4, 10))
            return panel

        def _bind_scroll_to_widget(self, widget: tk.Widget) -> None:
            widget.bind("<MouseWheel>", self._on_mousewheel, add="+")
            widget.bind("<Button-4>", self._on_mousewheel_linux_up, add="+")
            widget.bind("<Button-5>", self._on_mousewheel_linux_down, add="+")

        def _on_mousewheel(self, event: Any) -> str | None:
            if self._scroll_canvas is None:
                return None
            delta = int(-1 * (event.delta / 120)) if getattr(event, "delta", 0) else 0
            self._scroll_canvas.yview_scroll(delta, "units")
            return "break"

        def _on_mousewheel_linux_up(self, _event: Any) -> str | None:
            if self._scroll_canvas is None:
                return None
            self._scroll_canvas.yview_scroll(-3, "units")
            return "break"

        def _on_mousewheel_linux_down(self, _event: Any) -> str | None:
            if self._scroll_canvas is None:
                return None
            self._scroll_canvas.yview_scroll(3, "units")
            return "break"

        def _start_json_command(
            self,
            *,
            tool_id: str,
            action_label: str,
            command: CommandSpec,
            on_success: Callable[[dict[str, Any]], None],
        ) -> None:
            with self._process_lock:
                existing = self._active_processes.get(tool_id)
                if existing is not None and existing.poll() is None:
                    messagebox.showinfo("Панель Telegram", "Сначала дождись завершения текущего действия или нажми `Стоп`.")
                    return

            command_text = shlex.join(command.argv)
            self._status_var_for_tool(tool_id).set(f"Выполняется: {action_label}")
            self._set_tool_busy(tool_id, True)
            self._log_event(tool_id, f"Старт: {action_label}")
            self._log_event(tool_id, f"Команда: {command_text}")

            def _worker() -> None:
                completed_payload: dict[str, Any] | None = None
                error_text = ""
                stopped = False
                proc: subprocess.Popen[str] | None = None
                try:
                    proc = subprocess.Popen(
                        command.argv,
                        cwd=str(command.cwd),
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                    )
                    with self._process_lock:
                        self._active_processes[tool_id] = proc
                    stdout, stderr = proc.communicate()
                    stopped = proc.returncode in (-15, -9)
                    if proc.returncode == 0:
                        completed_payload = parse_json_payload(stdout)
                    else:
                        error_text = (stderr or stdout or "").strip() or f"command failed with code {proc.returncode}"
                except Exception as exc:
                        error_text = str(exc)
                finally:
                    with self._process_lock:
                        current = self._active_processes.get(tool_id)
                        if current is proc:
                            self._active_processes.pop(tool_id, None)
                self._ui_queue.put(
                    (
                        tool_id,
                        action_label,
                        completed_payload,
                        error_text,
                        stopped,
                        on_success,
                    )
                )

            threading.Thread(target=_worker, daemon=True).start()

        def _drain_ui_queue(self) -> None:
            while True:
                try:
                    (
                        tool_id,
                        action_label,
                        payload,
                        error_text,
                        stopped,
                        on_success,
                    ) = self._ui_queue.get_nowait()
                except queue.Empty:
                    break
                self._complete_json_command(
                    tool_id=tool_id,
                    action_label=action_label,
                    payload=payload,
                    error_text=error_text,
                    stopped=stopped,
                    on_success=on_success,
                )
            if self.winfo_exists():
                self.after(120, self._drain_ui_queue)

        def _complete_json_command(
            self,
            *,
            tool_id: str,
            action_label: str,
            payload: dict[str, Any] | None,
            error_text: str,
            stopped: bool,
            on_success: Callable[[dict[str, Any]], None],
        ) -> None:
            self._set_tool_busy(tool_id, False)
            if stopped:
                self._status_var_for_tool(tool_id).set("Остановлено")
                self._log_event(tool_id, f"Остановлено: {action_label}")
                return
            if error_text:
                self._status_var_for_tool(tool_id).set("Ошибка")
                self._log_event(tool_id, f"Ошибка: {action_label}")
                self._log_event(tool_id, error_text)
                messagebox.showerror("Панель Telegram", error_text)
                return
            assert payload is not None
            self._status_var_for_tool(tool_id).set("Завершено")
            self._log_event(tool_id, f"Завершено: {action_label}")
            on_success(payload)

        def _stop_tool_process(self, tool_id: str) -> None:
            with self._process_lock:
                proc = self._active_processes.get(tool_id)
            if proc is None or proc.poll() is not None:
                self._status_var_for_tool(tool_id).set("Нет активного действия")
                self._log_event(tool_id, "Попытка остановки: активный процесс не найден.")
                return
            self._status_var_for_tool(tool_id).set("Останавливается")
            self._log_event(tool_id, "Остановка активного процесса...")
            try:
                proc.terminate()
                self.after(1500, lambda: self._kill_if_needed(tool_id, proc))
            except Exception as exc:
                self._log_event(tool_id, f"Не удалось остановить процесс: {exc}")

        def _kill_if_needed(self, tool_id: str, proc: subprocess.Popen[str]) -> None:
            if proc.poll() is not None:
                return
            self._log_event(tool_id, "Процесс не завершился после terminate, отправляю kill.")
            try:
                proc.kill()
            except Exception as exc:
                self._log_event(tool_id, f"Не удалось завершить процесс kill: {exc}")

        def _build_ui(self) -> None:
            outer = ttk.Frame(self, style="App.TFrame", padding=20)
            outer.pack(fill=tk.BOTH, expand=True)

            header = ttk.Frame(outer, style="App.TFrame")
            header.pack(fill="x")
            hero = ttk.Frame(header, style="App.TFrame")
            hero.pack(side=tk.LEFT, fill="x", expand=True)
            ttk.Label(hero, text="Центр управления Telegram", style="HeroTitle.TLabel").pack(anchor="w")
            ttk.Label(hero, textvariable=self.summary_var, style="HeroSub.TLabel").pack(
                anchor="w", pady=(4, 0)
            )
            header_actions = ttk.Frame(header, style="App.TFrame")
            header_actions.pack(side=tk.RIGHT)
            ttk.Button(
                header_actions,
                text="Обновить профили",
                command=self._reload_profiles,
            ).pack(side=tk.LEFT)

            ttk.Separator(outer, orient="horizontal").pack(fill="x", pady=(16, 18))

            scroll_host = ttk.Frame(outer, style="App.TFrame")
            scroll_host.pack(fill=tk.BOTH, expand=True)
            canvas = tk.Canvas(
                scroll_host,
                bg=self._colors["bg"],
                highlightthickness=0,
                borderwidth=0,
            )
            scrollbar = ttk.Scrollbar(scroll_host, orient="vertical", command=canvas.yview)
            canvas.configure(yscrollcommand=scrollbar.set)
            canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
            content = ttk.Frame(canvas, style="App.TFrame")
            window_id = canvas.create_window((0, 0), window=content, anchor="nw")
            self._scroll_canvas = canvas

            def _sync_scrollregion(_event: object) -> None:
                canvas.configure(scrollregion=canvas.bbox("all"))

            def _sync_content_width(event: object) -> None:
                width = getattr(event, "width", None)
                if width:
                    canvas.itemconfigure(window_id, width=width)

            content.bind("<Configure>", _sync_scrollregion)
            canvas.bind("<Configure>", _sync_content_width)
            self._bind_scroll_to_widget(canvas)
            self.bind_all("<MouseWheel>", self._on_mousewheel, add="+")
            self.bind_all("<Button-4>", self._on_mousewheel_linux_up, add="+")
            self.bind_all("<Button-5>", self._on_mousewheel_linux_down, add="+")

            self._build_profile_section(content)
            self._build_tool_selector(content)
            self._build_tool_content(content)

        def _build_profile_section(self, parent: ttk.Frame) -> None:
            body = self._create_card(
                parent,
                "1. Telegram-профиль",
                "Сначала выбери рабочего пользователя Telegram. Этот профиль будет использован в запуске сессии и связанных действиях.",
            )
            body.columnconfigure(0, weight=1)
            body.columnconfigure(1, weight=1)
            body.columnconfigure(2, weight=0)
            body.columnconfigure(3, weight=0)

            ttk.Label(body, text="Корень профилей", style="Field.TLabel").grid(
                row=0, column=0, sticky="w"
            )
            ttk.Entry(body, textvariable=self.output_root_var).grid(
                row=1, column=0, columnspan=2, sticky="ew", pady=(4, 12)
            )
            ttk.Button(body, text="Перечитать", command=self._reload_profiles).grid(
                row=1, column=2, sticky="ew", padx=(10, 0)
            )

            ttk.Label(body, text="Текущий пользователь", style="Field.TLabel").grid(
                row=2, column=0, sticky="w"
            )
            self.profile_combo = ttk.Combobox(
                body,
                textvariable=self.profile_choice_var,
                state="readonly",
            )
            self.profile_combo.grid(
                row=3, column=0, sticky="ew", pady=(4, 0)
            )
            self.profile_combo.bind("<<ComboboxSelected>>", self._on_profile_select)
            action_row = ttk.Frame(body, style="Card.TFrame")
            action_row.grid(row=3, column=1, columnspan=3, sticky="ew", padx=(10, 0), pady=(4, 0))
            ttk.Button(
                action_row,
                text="Запустить",
                style="Accent.TButton",
                command=self._launch_selected_profile,
            ).pack(side=tk.LEFT)
            ttk.Button(
                action_row,
                text="Обновить статус",
                command=self._refresh_selected_profile_status,
            ).pack(side=tk.LEFT, padx=(10, 0))
            ttk.Button(
                action_row,
                text="Добавить / подключить профили",
                command=self._open_profile_manager,
            ).pack(side=tk.LEFT, padx=(10, 0))

            ttk.Label(body, text="Детали профиля", style="Field.TLabel").grid(
                row=4, column=0, sticky="w", pady=(16, 0)
            )
            self.profile_details = self._create_readonly_text(body, height=5)
            self.profile_details.grid(row=5, column=0, columnspan=4, sticky="nsew", pady=(6, 0))

        def _build_tool_selector(self, parent: ttk.Frame) -> None:
            body = self._create_card(
                parent,
                "2. Выбор инструмента",
                "Нажми нужную кнопку старта. Ниже откроется только один рабочий экран, чтобы не путаться.",
            )
            selector = ttk.Frame(body, style="Card.TFrame")
            selector.pack(fill="x")

            tools = [
                ("telegram_invite_manager", "Старт инвайтов"),
                ("telegram_session_runner", "Старт сессии"),
            ]
            for tool_id, label in tools:
                button = tk.Button(
                    selector,
                    text=label,
                    font=self._fonts["label"],
                    bd=0,
                    padx=28,
                    pady=16,
                    relief="flat",
                    command=lambda current=tool_id: self._switch_tool(current),
                )
                button.pack(side=tk.LEFT, padx=(0, 10))
                self._tool_buttons[tool_id] = button
            ttk.Label(
                body,
                text="`Старт инвайтов` открывает загрузку списка username из файла. `Старт сессии` открывает запуск random walk и список адресатов сообщений.",
                style="CardSubtitle.TLabel",
            ).pack(anchor="w", pady=(10, 0))

        def _build_tool_content(self, parent: ttk.Frame) -> None:
            container = ttk.Frame(parent, style="App.TFrame")
            container.pack(fill=tk.BOTH, expand=True)

            invite_frame = ttk.Frame(container, style="App.TFrame")
            session_frame = ttk.Frame(container, style="App.TFrame")
            invite_frame.grid(row=0, column=0, sticky="nsew")
            session_frame.grid(row=0, column=0, sticky="nsew")
            container.columnconfigure(0, weight=1)
            container.rowconfigure(0, weight=1)

            self._tool_frames["telegram_invite_manager"] = invite_frame
            self._tool_frames["telegram_session_runner"] = session_frame

            self._build_invite_view(invite_frame)
            self._build_session_view(session_frame)

        def _build_invite_view(self, parent: ttk.Frame) -> None:
            body = self._create_card(
                parent,
                "Инструмент: Инвайты по списку",
                "Загрузи файл с username, создай задачу и смотри следующих пользователей. Это отдельный режим и он не смешивается с отправкой сообщений.",
                expand=True,
            )
            body.columnconfigure(0, weight=1)
            body.columnconfigure(1, weight=0)

            top_buttons = ttk.Frame(body, style="Card.TFrame")
            top_buttons.grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 12))
            invite_start_button = ttk.Button(
                top_buttons,
                text="Старт инвайтов",
                style="Accent.TButton",
                command=self._invite_create_job,
            )
            invite_start_button.pack(side=tk.LEFT)
            self._register_busy_widget("telegram_invite_manager", invite_start_button)
            invite_status_button = ttk.Button(
                top_buttons,
                text="Статус задачи",
                command=self._invite_show_status,
            )
            invite_status_button.pack(side=tk.LEFT, padx=(10, 0))
            self._register_busy_widget("telegram_invite_manager", invite_status_button)
            invite_next_button = ttk.Button(
                top_buttons,
                text="Следующие username",
                command=self._invite_show_next,
            )
            invite_next_button.pack(side=tk.LEFT, padx=(10, 0))
            self._register_busy_widget("telegram_invite_manager", invite_next_button)
            invite_stop_button = ttk.Button(
                top_buttons,
                text="Стоп",
                command=lambda: self._stop_tool_process("telegram_invite_manager"),
                state="disabled",
            )
            invite_stop_button.pack(side=tk.LEFT, padx=(10, 0))
            self._register_stop_widget("telegram_invite_manager", invite_stop_button)
            ttk.Label(
                top_buttons,
                textvariable=self.invite_status_var,
                style="CardSubtitle.TLabel",
            ).pack(side=tk.LEFT, padx=(16, 0))

            ttk.Label(body, text="Шаг 1. Ссылка или ID чата", style="Field.TLabel").grid(
                row=1, column=0, sticky="w"
            )
            ttk.Entry(body, textvariable=self.invite_chat_url_var).grid(
                row=2, column=0, columnspan=2, sticky="ew", pady=(4, 10)
            )

            ttk.Label(body, text="Шаг 2. Файл со списком username с компьютера", style="Field.TLabel").grid(
                row=3, column=0, sticky="w"
            )
            file_row = ttk.Frame(body, style="Card.TFrame")
            file_row.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(4, 10))
            file_row.columnconfigure(0, weight=1)
            ttk.Entry(file_row, textvariable=self.invite_input_path_var).grid(
                row=0, column=0, sticky="ew"
            )
            invite_choose_file_button = ttk.Button(
                file_row,
                text="Загрузить TXT / CSV / JSON",
                command=self._choose_invite_input,
            )
            invite_choose_file_button.grid(row=0, column=1, padx=(10, 0))
            self._register_busy_widget("telegram_invite_manager", invite_choose_file_button)

            ttk.Label(body, text="Шаг 3. Папка задачи", style="Field.TLabel").grid(
                row=5, column=0, sticky="w"
            )
            ttk.Entry(body, textvariable=self.invite_job_dir_var).grid(
                row=6, column=0, columnspan=2, sticky="ew", pady=(4, 10)
            )

            ttk.Label(
                body,
                text="Поддерживаются .txt, .csv и .json. Для .txt одна строка = один @username, consent=yes ставится автоматически.",
                style="CardSubtitle.TLabel",
            ).grid(row=7, column=0, columnspan=2, sticky="w")

            next_row = ttk.Frame(body, style="Card.TFrame")
            next_row.grid(row=8, column=0, columnspan=2, sticky="w", pady=(14, 0))
            ttk.Label(next_row, text="Сколько показать дальше", style="Field.TLabel").pack(
                side=tk.LEFT
            )
            ttk.Entry(next_row, textvariable=self.invite_limit_var, width=8).pack(
                side=tk.LEFT, padx=(10, 0)
            )

            ttk.Label(body, text="Что происходит сейчас", style="Field.TLabel").grid(
                row=9, column=0, sticky="w", pady=(16, 0)
            )
            self.invite_output = self._create_readonly_text(body, height=16)
            self.invite_output.grid(row=10, column=0, columnspan=2, sticky="nsew", pady=(6, 0))
            self._bind_scroll_to_widget(self.invite_output)
            body.rowconfigure(10, weight=1)

        def _build_session_view(self, parent: ttk.Frame) -> None:
            body = self._create_card(
                parent,
                "Инструмент: Сессия и сообщения",
                "Здесь выбирается список адресатов сообщений и запускается сам session runner. Этот экран никак не вмешивается в режим инвайтов.",
                expand=True,
            )
            body.columnconfigure(0, weight=1)
            body.columnconfigure(1, weight=0)

            top_buttons = ttk.Frame(body, style="Card.TFrame")
            top_buttons.grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 12))
            session_start_button = ttk.Button(
                top_buttons,
                text="Старт сессии",
                style="Accent.TButton",
                command=self._session_run,
            )
            session_start_button.pack(side=tk.LEFT)
            self._register_busy_widget("telegram_session_runner", session_start_button)
            session_plan_button = ttk.Button(
                top_buttons,
                text="Показать план",
                command=self._session_show_plan,
            )
            session_plan_button.pack(side=tk.LEFT, padx=(10, 0))
            self._register_busy_widget("telegram_session_runner", session_plan_button)
            session_stop_button = ttk.Button(
                top_buttons,
                text="Стоп",
                command=lambda: self._stop_tool_process("telegram_session_runner"),
                state="disabled",
            )
            session_stop_button.pack(side=tk.LEFT, padx=(10, 0))
            self._register_stop_widget("telegram_session_runner", session_stop_button)
            ttk.Label(
                top_buttons,
                textvariable=self.session_status_var,
                style="CardSubtitle.TLabel",
            ).pack(side=tk.LEFT, padx=(16, 0))

            ttk.Label(body, text="Шаг 1. Конфиг режима сессии", style="Field.TLabel").grid(
                row=1, column=0, sticky="w"
            )
            config_row = ttk.Frame(body, style="Card.TFrame")
            config_row.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(4, 10))
            config_row.columnconfigure(0, weight=1)
            ttk.Entry(config_row, textvariable=self.session_config_path_var).grid(
                row=0, column=0, sticky="ew"
            )
            session_choose_config_button = ttk.Button(
                config_row,
                text="Выбрать конфиг",
                command=self._choose_session_config,
            )
            session_choose_config_button.grid(row=0, column=1, padx=(10, 0))
            self._register_busy_widget("telegram_session_runner", session_choose_config_button)
            session_load_targets_button = ttk.Button(
                config_row,
                text="Загрузить список адресатов",
                command=self._load_session_targets,
            )
            session_load_targets_button.grid(row=0, column=2, padx=(10, 0))
            self._register_busy_widget("telegram_session_runner", session_load_targets_button)

            ttk.Label(body, text="Шаг 2. Список адресатов сообщений", style="Field.TLabel").grid(
                row=3, column=0, sticky="w"
            )
            recipients_row = ttk.Frame(body, style="Card.TFrame")
            recipients_row.grid(row=4, column=0, columnspan=2, sticky="nsew", pady=(6, 0))
            recipients_row.columnconfigure(0, weight=1)
            self.session_targets_list = self._create_listbox(
                recipients_row,
                selectmode=tk.EXTENDED,
                height=8,
            )
            self.session_targets_list.grid(row=0, column=0, rowspan=8, sticky="nsew")
            self._bind_scroll_to_widget(self.session_targets_list)
            session_remove_target_button = ttk.Button(
                recipients_row,
                text="Удалить выбранных",
                command=self._remove_session_targets,
            )
            session_remove_target_button.grid(row=0, column=1, sticky="ew", padx=(10, 0))
            self._register_busy_widget("telegram_session_runner", session_remove_target_button)

            ttk.Label(recipients_row, text="Добавить новый адресат", style="Field.TLabel").grid(
                row=1, column=1, sticky="w", padx=(10, 0), pady=(12, 0)
            )
            ttk.Label(recipients_row, text="Username или @ссылка", style="Field.TLabel").grid(
                row=2, column=1, sticky="w", padx=(10, 0), pady=(8, 0)
            )
            ttk.Entry(recipients_row, textvariable=self.session_new_target_var).grid(
                row=3, column=1, sticky="ew", padx=(10, 0), pady=(4, 0)
            )
            ttk.Label(recipients_row, text="Понятное название", style="Field.TLabel").grid(
                row=4, column=1, sticky="w", padx=(10, 0), pady=(8, 0)
            )
            ttk.Entry(recipients_row, textvariable=self.session_new_target_label_var).grid(
                row=5, column=1, sticky="ew", padx=(10, 0), pady=(4, 0)
            )
            ttk.Label(recipients_row, text="Тип адресата", style="Field.TLabel").grid(
                row=6, column=1, sticky="w", padx=(10, 0), pady=(8, 0)
            )
            kind_combo = ttk.Combobox(
                recipients_row,
                textvariable=self.session_new_target_kind_var,
                state="readonly",
                values=["Контакт", "Группа"],
            )
            kind_combo.grid(row=7, column=1, sticky="ew", padx=(10, 0), pady=(4, 0))
            session_add_target_button = ttk.Button(
                recipients_row,
                text="Добавить адресата",
                command=self._add_session_target,
            )
            session_add_target_button.grid(row=8, column=1, sticky="ew", padx=(10, 0), pady=(10, 0))
            self._register_busy_widget("telegram_session_runner", session_add_target_button)

            ttk.Label(
                recipients_row,
                text="Сначала введи @username. Во второй строке можно дать понятное имя, а ниже выбрать тип: контакт или группа.",
                style="CardSubtitle.TLabel",
            ).grid(row=9, column=1, sticky="w", padx=(10, 0), pady=(10, 0))

            ttk.Checkbutton(
                body,
                text="Отправлять сообщения автоматически",
                variable=self.session_auto_send_var,
            ).grid(row=5, column=0, sticky="w", pady=(14, 0))

            ttk.Label(
                body,
                text="Текущий профиль сверху будет автоматически подставлен в runtime-config перед запуском.",
                style="CardSubtitle.TLabel",
            ).grid(row=6, column=0, columnspan=2, sticky="w", pady=(6, 0))

            ttk.Label(body, text="Что происходит сейчас", style="Field.TLabel").grid(
                row=7, column=0, sticky="w", pady=(16, 0)
            )
            self.session_output = self._create_readonly_text(body, height=16)
            self.session_output.grid(row=8, column=0, columnspan=2, sticky="nsew", pady=(6, 0))
            self._bind_scroll_to_widget(self.session_output)
            body.rowconfigure(8, weight=1)
            body.rowconfigure(4, weight=0)

        def _refresh_summary(self) -> None:
            selected_profile = self._selected_profile()
            profile_part = (
                format_profile_label(selected_profile) if selected_profile is not None else "профиль не выбран"
            )
            active_label = (
                "Инвайты по списку"
                if self._active_tool_id == "telegram_invite_manager"
                else "Сессия и сообщения"
            )
            self.summary_var.set(
                f"Профилей найдено: {len(self._profiles)} · Выбранный профиль: {profile_part} · Активный режим: {active_label}"
            )

        def _reload_profiles(
            self,
            initial: bool = False,
            preferred_profile_dir: str | None = None,
        ) -> None:
            try:
                self._profiles = list_portable_profiles(self.output_root_var.get())
            except Exception as exc:  # pragma: no cover - GUI fallback
                messagebox.showerror("Панель Telegram", f"Не удалось прочитать профили:\n{exc}")
                if initial:
                    raise
                return

            labels = [format_profile_label(profile) for profile in self._profiles]
            if self.profile_combo is not None:
                self.profile_combo["values"] = labels

            if not self._profiles:
                self.profile_choice_var.set("")
                self._set_readonly_text(
                    self.profile_details,
                    "Профили не найдены. Проверь корень профилей и импортируй нужный tdata.",
                )
                self._refresh_summary()
                return

            index = 0
            if preferred_profile_dir:
                for candidate_index, profile in enumerate(self._profiles):
                    if str(profile.get("profile_dir")) == str(preferred_profile_dir):
                        index = candidate_index
                        break
            if self.profile_combo is not None:
                self.profile_combo.current(index)
            self._show_profile(self._profiles[index])
            self._refresh_summary()

        def _selected_profile(self) -> dict[str, Any] | None:
            if self.profile_combo is None:
                return None
            index = self.profile_combo.current()
            if index < 0 or index >= len(self._profiles):
                return None
            return self._profiles[index]

        def _show_profile(self, profile: dict[str, Any]) -> None:
            self._set_readonly_text(self.profile_details, format_profile_details(profile))

        def _on_profile_select(self, _event: object) -> None:
            profile = self._selected_profile()
            if profile is not None:
                self._show_profile(profile)
                self._refresh_summary()

        def _launch_selected_profile(self) -> None:
            profile = self._selected_profile()
            if profile is None:
                messagebox.showinfo("Панель Telegram", "Сначала выбери Telegram-профиль.")
                return
            try:
                result = launch_profile(str(profile.get("profile_dir") or ""))
            except Exception as exc:  # pragma: no cover - GUI fallback
                messagebox.showerror("Панель Telegram", f"Не удалось запустить профиль:\n{exc}")
                return
            self._reload_profiles(preferred_profile_dir=str(profile.get("profile_dir") or ""))
            messagebox.showinfo(
                "Запуск профиля",
                json.dumps(result, ensure_ascii=False, indent=2),
            )

        def _refresh_selected_profile_status(self) -> None:
            profile = self._selected_profile()
            if profile is None:
                messagebox.showinfo("Панель Telegram", "Сначала выбери Telegram-профиль.")
                return
            try:
                fresh = get_profile_status(str(profile.get("profile_dir") or ""))
            except Exception as exc:  # pragma: no cover - GUI fallback
                messagebox.showerror("Панель Telegram", f"Не удалось обновить статус:\n{exc}")
                return
            index = self.profile_combo.current() if self.profile_combo is not None else -1
            if 0 <= index < len(self._profiles):
                self._profiles[index] = fresh
            self._show_profile(fresh)
            self._refresh_summary()

        def _sync_invite_job_dir(self, *_args: object) -> None:
            chat_url = self.invite_chat_url_var.get().strip()
            if not chat_url or self.invite_job_dir_var.get().strip():
                return
            self.invite_job_dir_var.set(str(default_invite_job_dir(chat_url, DEFAULT_INVITE_OUTPUT_ROOT)))

        def _switch_tool(self, tool_id: str) -> None:
            self._active_tool_id = tool_id
            for current_tool_id, frame in self._tool_frames.items():
                if current_tool_id == tool_id:
                    frame.tkraise()
                button = self._tool_buttons[current_tool_id]
                if current_tool_id == tool_id:
                    button.configure(
                        bg=self._colors["accent"],
                        fg=self._colors["accent_text"],
                        activebackground=self._colors["accent_active"],
                        activeforeground=self._colors["accent_text"],
                    )
                else:
                    button.configure(
                        bg=self._colors["inactive_button"],
                        fg=self._colors["text"],
                        activebackground=self._colors["field"],
                        activeforeground=self._colors["text"],
                    )
            if tool_id == "telegram_invite_manager":
                self._set_readonly_text(
                    self.invite_output,
                    "\n".join(
                        [
                            "Инвайты по списку",
                            "1. Укажи ссылку или ID чата.",
                            "2. Нажми `Загрузить TXT / CSV / JSON` и выбери файл с компьютера.",
                            "3. Нажми `Старт инвайтов`.",
                        ]
                    ),
                )
            elif tool_id == "telegram_session_runner":
                self._set_readonly_text(
                    self.session_output,
                    "\n".join(
                        [
                            "Сессия и сообщения",
                            "1. Выбери конфиг режима сессии.",
                            "2. Загрузить список адресатов или добавь их вручную.",
                            "3. Нажми `Старт сессии`.",
                        ]
                    ),
                )
            self._refresh_summary()

        def _build_profile_manager_form(self, parent: ttk.Frame) -> None:
            parent.columnconfigure(0, weight=1)
            parent.columnconfigure(1, weight=1)

            import_panel = self._create_inline_panel(
                parent,
                "Добавить нового пользователя",
                "Импортируй `tdata.zip`, и профиль сразу появится в списке.",
            )
            import_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
            import_panel.columnconfigure(0, weight=1)

            tk.Label(
                import_panel,
                text="Файл tdata.zip",
                bg=self._colors["field"],
                fg=self._colors["muted"],
                font=self._fonts["small"],
                anchor="w",
            ).grid(row=2, column=0, sticky="w")
            import_path_row = ttk.Frame(import_panel, style="Card.TFrame")
            import_path_row.grid(row=3, column=0, sticky="ew", pady=(4, 8))
            import_path_row.columnconfigure(0, weight=1)
            ttk.Entry(import_path_row, textvariable=self.import_zip_var).grid(row=0, column=0, sticky="ew")
            ttk.Button(import_path_row, text="Выбрать", command=self._choose_import_zip).grid(
                row=0, column=1, padx=(10, 0)
            )

            tk.Label(
                import_panel,
                text="Имя профиля",
                bg=self._colors["field"],
                fg=self._colors["muted"],
                font=self._fonts["small"],
                anchor="w",
            ).grid(row=4, column=0, sticky="w")
            ttk.Entry(import_panel, textvariable=self.import_profile_name_var).grid(
                row=5, column=0, sticky="ew", pady=(4, 8)
            )

            tk.Label(
                import_panel,
                text="Username аккаунта",
                bg=self._colors["field"],
                fg=self._colors["muted"],
                font=self._fonts["small"],
                anchor="w",
            ).grid(row=6, column=0, sticky="w")
            ttk.Entry(import_panel, textvariable=self.import_account_username_var).grid(
                row=7, column=0, sticky="ew", pady=(4, 8)
            )

            tk.Label(
                import_panel,
                text="Понятная метка",
                bg=self._colors["field"],
                fg=self._colors["muted"],
                font=self._fonts["small"],
                anchor="w",
            ).grid(row=8, column=0, sticky="w")
            ttk.Entry(import_panel, textvariable=self.import_account_label_var).grid(
                row=9, column=0, sticky="ew", pady=(4, 12)
            )
            ttk.Button(
                import_panel,
                text="Импортировать и запустить",
                style="Accent.TButton",
                command=self._import_profile,
            ).grid(row=10, column=0, sticky="e")

            adopt_panel = self._create_inline_panel(
                parent,
                "Подключить готовую папку",
                "Если профиль уже лежит на диске, просто добавь его в список без переимпорта.",
            )
            adopt_panel.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
            adopt_panel.columnconfigure(0, weight=1)

            tk.Label(
                adopt_panel,
                text="Папка профиля",
                bg=self._colors["field"],
                fg=self._colors["muted"],
                font=self._fonts["small"],
                anchor="w",
            ).grid(row=2, column=0, sticky="w")
            adopt_path_row = ttk.Frame(adopt_panel, style="Card.TFrame")
            adopt_path_row.grid(row=3, column=0, sticky="ew", pady=(4, 8))
            adopt_path_row.columnconfigure(0, weight=1)
            ttk.Entry(adopt_path_row, textvariable=self.adopt_profile_dir_var).grid(row=0, column=0, sticky="ew")
            ttk.Button(adopt_path_row, text="Выбрать", command=self._choose_adopt_dir).grid(
                row=0, column=1, padx=(10, 0)
            )

            tk.Label(
                adopt_panel,
                text="Имя профиля",
                bg=self._colors["field"],
                fg=self._colors["muted"],
                font=self._fonts["small"],
                anchor="w",
            ).grid(row=4, column=0, sticky="w")
            ttk.Entry(adopt_panel, textvariable=self.adopt_profile_name_var).grid(
                row=5, column=0, sticky="ew", pady=(4, 8)
            )

            tk.Label(
                adopt_panel,
                text="Username аккаунта",
                bg=self._colors["field"],
                fg=self._colors["muted"],
                font=self._fonts["small"],
                anchor="w",
            ).grid(row=6, column=0, sticky="w")
            ttk.Entry(adopt_panel, textvariable=self.adopt_account_username_var).grid(
                row=7, column=0, sticky="ew", pady=(4, 8)
            )

            tk.Label(
                adopt_panel,
                text="Понятная метка",
                bg=self._colors["field"],
                fg=self._colors["muted"],
                font=self._fonts["small"],
                anchor="w",
            ).grid(row=8, column=0, sticky="w")
            ttk.Entry(adopt_panel, textvariable=self.adopt_account_label_var).grid(
                row=9, column=0, sticky="ew", pady=(4, 12)
            )
            ttk.Button(
                adopt_panel,
                text="Подключить профиль",
                command=self._adopt_profile,
            ).grid(row=10, column=0, sticky="e")

        def _open_profile_manager(self) -> None:
            if self.profile_manager_window is not None and self.profile_manager_window.winfo_exists():
                self.profile_manager_window.lift()
                self.profile_manager_window.focus_force()
                return

            window = tk.Toplevel(self)
            window.title("Управление профилями Telegram")
            window.geometry("1200x620")
            window.minsize(1000, 540)
            window.configure(bg=self._colors["bg"])
            window.transient(self)
            self.profile_manager_window = window

            def _on_close() -> None:
                self.profile_manager_window = None
                window.destroy()

            window.protocol("WM_DELETE_WINDOW", _on_close)

            outer = ttk.Frame(window, style="App.TFrame", padding=20)
            outer.pack(fill=tk.BOTH, expand=True)
            ttk.Label(
                outer,
                text="Добавление и подключение Telegram-профилей",
                style="HeroTitle.TLabel",
            ).pack(anchor="w")
            ttk.Label(
                outer,
                text="Здесь можно импортировать нового пользователя по tdata.zip или принять в управление уже готовую папку профиля.",
                style="HeroSub.TLabel",
            ).pack(anchor="w", pady=(6, 16))

            form = ttk.Frame(outer, style="App.TFrame")
            form.pack(fill=tk.BOTH, expand=True)
            self._build_profile_manager_form(form)

        def _choose_import_zip(self) -> None:
            if filedialog is None:  # pragma: no cover - depends on tkinter extras
                return
            selected = filedialog.askopenfilename(
                title="Выбери tdata.zip",
                filetypes=[("ZIP архивы", "*.zip"), ("Все файлы", "*")],
            )
            if selected:
                self.import_zip_var.set(selected)
                if not self.import_profile_name_var.get().strip():
                    self.import_profile_name_var.set(Path(selected).stem)

        def _choose_adopt_dir(self) -> None:
            if filedialog is None:  # pragma: no cover - depends on tkinter extras
                return
            selected = filedialog.askdirectory(title="Выбери существующую папку Telegram")
            if selected:
                self.adopt_profile_dir_var.set(selected)
                if not self.adopt_profile_name_var.get().strip():
                    self.adopt_profile_name_var.set(Path(selected).name)

        def _choose_invite_input(self) -> None:
            if filedialog is None:  # pragma: no cover - depends on tkinter extras
                return
            selected = filedialog.askopenfilename(
                title="Выбери файл со списком username",
                filetypes=[
                    ("Поддерживаемые файлы", "*.txt *.csv *.json"),
                    ("Текстовые файлы", "*.txt"),
                    ("CSV", "*.csv"),
                    ("JSON", "*.json"),
                    ("Все файлы", "*"),
                ],
            )
            if selected:
                self.invite_input_path_var.set(selected)
                self.invite_status_var.set("Файл списка выбран")
                self._log_event("telegram_invite_manager", f"Выбран файл списка: {selected}")

        def _choose_session_config(self) -> None:
            if filedialog is None:  # pragma: no cover - depends on tkinter extras
                return
            selected = filedialog.askopenfilename(
                title="Выбери конфиг режима сессии",
                filetypes=[("JSON", "*.json"), ("Все файлы", "*")],
            )
            if selected:
                self.session_config_path_var.set(selected)
                self.session_status_var.set("Конфиг выбран")
                self._log_event("telegram_session_runner", f"Выбран конфиг: {selected}")
                self._load_session_targets(show_feedback=False)

        def _import_profile(self) -> None:
            zip_path = self.import_zip_var.get().strip()
            if not zip_path:
                messagebox.showinfo("Панель Telegram", "Сначала выбери файл tdata.zip.")
                return
            try:
                result = import_tdata_profile(
                    zip_path=zip_path,
                    output_root=self.output_root_var.get(),
                    profile_name=self.import_profile_name_var.get(),
                    account_username=self.import_account_username_var.get(),
                    account_label=self.import_account_label_var.get(),
                    launch=True,
                )
            except Exception as exc:  # pragma: no cover - GUI fallback
                messagebox.showerror("Панель Telegram", f"Импорт профиля не удался:\n{exc}")
                return
            self._reload_profiles(preferred_profile_dir=str(result.get("profile_dir") or ""))
            messagebox.showinfo(
                "Импорт профиля",
                f"Профиль импортирован и добавлен в список.\n\n{json.dumps(result, ensure_ascii=False, indent=2)}",
            )

        def _adopt_profile(self) -> None:
            profile_dir = self.adopt_profile_dir_var.get().strip()
            if not profile_dir:
                messagebox.showinfo("Панель Telegram", "Сначала выбери существующую portable-папку.")
                return
            try:
                result = adopt_existing_profile(
                    profile_dir=profile_dir,
                    profile_name=self.adopt_profile_name_var.get(),
                    account_username=self.adopt_account_username_var.get(),
                    account_label=self.adopt_account_label_var.get(),
                )
            except Exception as exc:  # pragma: no cover - GUI fallback
                messagebox.showerror("Панель Telegram", f"Подключение профиля не удалось:\n{exc}")
                return
            self._reload_profiles(preferred_profile_dir=str(result.get("profile_dir") or ""))
            messagebox.showinfo(
                "Подключение профиля",
                f"Папка профиля подключена и добавлена в список.\n\n{json.dumps(result, ensure_ascii=False, indent=2)}",
            )

        def _invite_resolved_job_dir(self) -> Path:
            job_dir = self.invite_job_dir_var.get().strip()
            if job_dir:
                return Path(job_dir).expanduser().resolve()
            chat_url = self.invite_chat_url_var.get().strip()
            if not chat_url:
                raise ValueError("Укажи ссылку или ID чата.")
            resolved = default_invite_job_dir(chat_url, DEFAULT_INVITE_OUTPUT_ROOT)
            self.invite_job_dir_var.set(str(resolved))
            return resolved

        def _invite_create_job(self) -> None:
            chat_url = self.invite_chat_url_var.get().strip()
            input_path = self.invite_input_path_var.get().strip()
            if not chat_url:
                messagebox.showinfo("Панель Telegram", "Укажи ссылку или ID чата.")
                return
            if not input_path:
                messagebox.showinfo("Панель Telegram", "Выбери файл со списком username.")
                return
            try:
                command = invite_manager_init_command(
                    chat_url=chat_url,
                    input_path=input_path,
                    job_dir=self.invite_job_dir_var.get().strip() or None,
                )
            except Exception as exc:
                messagebox.showerror("Панель Telegram", f"Не удалось создать invite-задачу:\n{exc}")
                return
            self._start_json_command(
                tool_id="telegram_invite_manager",
                action_label="создание invite-задачи",
                command=command,
                on_success=self._on_invite_init_success,
            )

        def _invite_show_status(self) -> None:
            try:
                command = invite_manager_status_command(self._invite_resolved_job_dir())
            except Exception as exc:
                messagebox.showerror("Панель Telegram", f"Не удалось прочитать статус:\n{exc}")
                return
            self._start_json_command(
                tool_id="telegram_invite_manager",
                action_label="чтение статуса invite-задачи",
                command=command,
                on_success=lambda payload: self._set_readonly_text(
                    self.invite_output, format_invite_status_payload(payload)
                ),
            )

        def _invite_show_next(self) -> None:
            try:
                limit = max(int(self.invite_limit_var.get() or "10"), 1)
            except ValueError:
                limit = 10
            try:
                command = invite_manager_next_command(self._invite_resolved_job_dir(), limit=limit)
            except Exception as exc:
                messagebox.showerror("Панель Telegram", f"Не удалось получить следующих пользователей:\n{exc}")
                return
            self._start_json_command(
                tool_id="telegram_invite_manager",
                action_label="получение следующей пачки username",
                command=command,
                on_success=lambda payload: self._set_readonly_text(
                    self.invite_output, format_invite_status_payload(payload)
                ),
            )

        def _render_session_targets(self) -> None:
            if self.session_targets_list is None:
                return
            self.session_targets_list.delete(0, tk.END)
            for item in self._session_targets:
                self.session_targets_list.insert(tk.END, format_session_target_label(item))

        def _load_session_targets(self, show_feedback: bool = True) -> None:
            try:
                self._session_targets = session_message_targets(self.session_config_path_var.get())
            except Exception as exc:
                messagebox.showerror("Панель Telegram", f"Не удалось прочитать конфиг режима сессии:\n{exc}")
                return
            self._render_session_targets()
            self.session_status_var.set("Список адресатов загружен")
            self._log_event(
                "telegram_session_runner",
                f"Загружено адресатов из конфига: {len(self._session_targets)}",
            )
            self._set_readonly_text(
                self.session_output,
                "\n".join(
                    [
                        "Сессия и сообщения",
                        f"Конфиг: {self.session_config_path_var.get()}",
                        f"Загружено адресатов: {len(self._session_targets)}",
                        "Выше показан именно список адресатов сообщений.",
                    ]
                ),
            )
            if show_feedback:
                messagebox.showinfo(
                    "Панель Telegram",
                    f"Из конфига загружено адресатов: {len(self._session_targets)}",
                )

        def _add_session_target(self) -> None:
            raw_value = self.session_new_target_var.get().strip()
            if not raw_value:
                messagebox.showinfo("Панель Telegram", "Введи @username для добавления.")
                return
            if not USERNAME_RE.fullmatch(raw_value):
                messagebox.showerror("Панель Telegram", f"Некорректный username: {raw_value}")
                return
            handle = raw_value if raw_value.startswith("@") else f"@{raw_value}"
            normalized = handle.lower()
            for item in self._session_targets:
                if str(item.get("handle") or "").strip().lower() == normalized:
                    messagebox.showinfo("Панель Telegram", "Этот адресат уже есть в списке.")
                    return
            label = self.session_new_target_label_var.get().strip() or normalized
            kind = (
                "group"
                if self.session_new_target_kind_var.get().strip().lower().startswith("груп")
                else "contact"
            )
            self._session_targets.append(
                {
                    "target_id": f"manual_{normalized.lstrip('@')}",
                    "label": label,
                    "handle": normalized,
                    "kind": kind,
                }
            )
            self.session_new_target_var.set("")
            self.session_new_target_label_var.set("")
            self.session_new_target_kind_var.set("Контакт")
            self._render_session_targets()

        def _remove_session_targets(self) -> None:
            if self.session_targets_list is None:
                return
            selection = list(self.session_targets_list.curselection())
            if not selection:
                messagebox.showinfo("Панель Telegram", "Выдели одного или нескольких адресатов для удаления.")
                return
            keep = [
                item
                for index, item in enumerate(self._session_targets)
                if index not in set(selection)
            ]
            self._session_targets = keep
            self._render_session_targets()

        def _session_runtime_config_path(self) -> Path:
            temp_dir = Path("/tmp/telegram-control-center")
            temp_dir.mkdir(parents=True, exist_ok=True)
            return Path(
                tempfile.mkstemp(
                    prefix="session-runner-",
                    suffix=".json",
                    dir=str(temp_dir),
                )[1]
            )

        def _build_session_runtime_config(self) -> Path:
            if not self._session_targets:
                raise ValueError("Добавь хотя бы одного адресата для сообщений.")
            selected_profile = self._selected_profile()
            profile_dir = str(selected_profile.get("profile_dir") or "") if selected_profile else ""
            return build_session_runtime_config(
                base_config_path=self.session_config_path_var.get(),
                output_path=self._session_runtime_config_path(),
                message_targets=self._session_targets,
                portable_profile_dir=profile_dir,
                auto_send=bool(self.session_auto_send_var.get()),
            )

        def _session_show_plan(self) -> None:
            try:
                runtime_config = self._build_session_runtime_config()
                command = session_plan_command(config_path=runtime_config)
            except Exception as exc:
                messagebox.showerror("Панель Telegram", f"Не удалось построить session plan:\n{exc}")
                return
            self._start_json_command(
                tool_id="telegram_session_runner",
                action_label="построение session plan",
                command=command,
                on_success=lambda payload, runtime_config=runtime_config: self._on_session_plan_success(
                    payload,
                    runtime_config,
                ),
            )

        def _session_run(self) -> None:
            try:
                runtime_config = self._build_session_runtime_config()
                command = session_run_command(
                    config_path=runtime_config,
                    auto_send=bool(self.session_auto_send_var.get()),
                )
            except Exception as exc:
                messagebox.showerror("Панель Telegram", f"Не удалось запустить режим сессии:\n{exc}")
                return
            self._start_json_command(
                tool_id="telegram_session_runner",
                action_label="запуск session runner",
                command=command,
                on_success=lambda payload, runtime_config=runtime_config: self._on_session_run_success(
                    payload,
                    runtime_config,
                ),
            )

        def _on_invite_init_success(self, payload: dict[str, Any]) -> None:
            if payload.get("job_dir"):
                self.invite_job_dir_var.set(str(payload["job_dir"]))
            self._set_readonly_text(self.invite_output, format_invite_status_payload(payload))

        def _on_session_plan_success(self, payload: dict[str, Any], runtime_config: Path) -> None:
            summary = format_session_plan_payload(payload)
            summary += f"\n\nRuntime config:\n{runtime_config}"
            self._set_readonly_text(self.session_output, summary)

        def _on_session_run_success(self, payload: dict[str, Any], runtime_config: Path) -> None:
            summary = format_session_run_payload(payload)
            summary += f"\n\nRuntime config:\n{runtime_config}"
            self._set_readonly_text(self.session_output, summary)

else:

    class ToolPlatformPanel:
        def __init__(self, _registry_path: str) -> None:
            raise RuntimeError(
                "tkinter не установлен в этом окружении, поэтому графическую "
                "панель Telegram запустить нельзя."
            ) from TKINTER_IMPORT_ERROR


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="tool-platform-panel",
        description="Открыть русскую графическую панель управления Telegram-профилями и инструментами.",
    )
    parser.add_argument(
        "--registry",
        default=str(DEFAULT_REGISTRY_PATH),
        help="Path to tool registry JSON.",
    )
    args = parser.parse_args(argv)
    if tk is None:
        parser.exit(
            1,
            "tkinter не установлен в этом окружении; "
            "графическая панель недоступна.\n",
        )
    panel = ToolPlatformPanel(args.registry)
    panel.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
