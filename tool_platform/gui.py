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
import time
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
    DEFAULT_SESSION_RUNS_DIR,
    DEFAULT_SESSION_STATE_FILE,
    build_session_runtime_config,
    contact_job_snapshot,
    contact_add_batch_command,
    default_contact_add_job_dir,
    format_session_target_label,
    invite_manager_next_command,
    parse_json_payload,
    preview_invite_input_file,
    session_config_defaults,
    session_history_snapshot,
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


def format_profiles_overview(profiles: list[dict[str, Any]]) -> str:
    if not profiles:
        return "Профили пока не найдены."
    lines = ["Все профили"]
    for profile in profiles:
        account = profile.get("account") if isinstance(profile.get("account"), dict) else {}
        username = str(account.get("username") or "без username")
        label = str(account.get("label") or "").strip() or username
        state = "запущен" if profile.get("running") else "остановлен"
        profile_name = str(profile.get("profile_name") or "profile")
        lines.append(f"- {label} · {profile_name} · {state}")
    return "\n".join(lines)


def _format_username_block(title: str, usernames: list[str], *, empty_text: str) -> str:
    lines = [title]
    if not usernames:
        lines.append(empty_text)
        return "\n".join(lines)
    for item in usernames:
        lines.append(f"- {item}")
    return "\n".join(lines)


def format_contact_dashboard_snapshot(snapshot: dict[str, Any]) -> str:
    if str(snapshot.get("status") or "") == "missing":
        return "\n".join(
            [
                "Задача добавления контактов пока не создана.",
                f"Папка задачи: {snapshot.get('job_dir') or '-'}",
                "Выбери файл со списком и нажми `Старт добавления`.",
            ]
        )
    counts = snapshot.get("counts") if isinstance(snapshot.get("counts"), dict) else {}
    lines = [
        "Сводка задачи",
        f"Папка задачи: {snapshot.get('job_dir') or '-'}",
        f"Источник списка: {snapshot.get('source_file') or '-'}",
        f"Всего username: {snapshot.get('total_users') or 0}",
        f"Осталось: {snapshot.get('pending_total') or 0}",
        f"Добавлено: {snapshot.get('added_total') or 0}",
        f"Ошибок: {snapshot.get('failed_total') or 0}",
    ]
    if counts:
        lines.append("")
        lines.append("Статусы")
        for key, value in sorted(counts.items()):
            lines.append(f"- {key}: {value}")
    latest_runs = snapshot.get("latest_runs") if isinstance(snapshot.get("latest_runs"), list) else []
    if latest_runs:
        last_run = latest_runs[-1]
        lines.extend(
            [
                "",
                "Последний batch",
                (
                    f"- {last_run.get('execution_id') or '-'} · статус: {last_run.get('status') or '-'}"
                    f" · добавлено: {last_run.get('added_count') or 0}"
                    f" · ошибок: {last_run.get('failed_count') or 0}"
                ),
            ]
        )
    return "\n".join(lines)


def format_contact_history(snapshot: dict[str, Any]) -> str:
    history = snapshot.get("latest_runs") if isinstance(snapshot.get("latest_runs"), list) else []
    if not history:
        return "История batch-запусков\nПока нет запусков."
    lines = ["История batch-запусков"]
    for item in history[-8:]:
        lines.append(
            f"- {item.get('execution_id') or '-'} · {item.get('status') or '-'} · добавлено {item.get('added_count') or 0} · ошибок {item.get('failed_count') or 0} · осталось {item.get('remaining_candidates') or 0}"
        )
    return "\n".join(lines)


def format_contact_errors(snapshot: dict[str, Any]) -> str:
    errors = snapshot.get("latest_errors") if isinstance(snapshot.get("latest_errors"), list) else []
    if not errors:
        return "Последние ошибки\nСвежих ошибок не найдено."
    lines = ["Последние ошибки"]
    for item in errors:
        error_text = str(item.get("error") or "").strip() or str(item.get("outcome") or "-")
        lines.append(f"- {item.get('username') or '-'} · {error_text}")
    return "\n".join(lines)


def format_invite_input_preview(preview: dict[str, Any]) -> str:
    lines = [
        "Предпросмотр списка username",
        f"Файл: {preview.get('path') or '-'}",
        f"Формат: {preview.get('format') or '-'}",
        f"Строк прочитано: {preview.get('rows_total') or 0}",
        f"Уникальных username: {preview.get('unique_usernames') or 0}",
        f"Дубликатов: {preview.get('duplicates') or 0}",
        f"Некорректных строк: {preview.get('invalid_count') or 0}",
    ]
    usernames = preview.get("usernames") if isinstance(preview.get("usernames"), list) else []
    if usernames:
        lines.extend(["", "Первые username"])
        for item in usernames:
            lines.append(f"- {item}")
    invalid_entries = preview.get("invalid_entries") if isinstance(preview.get("invalid_entries"), list) else []
    if invalid_entries:
        lines.extend(["", "Некорректные строки"])
        for item in invalid_entries:
            lines.append(f"- {item}")
    return "\n".join(lines)


def format_session_dashboard_snapshot(snapshot: dict[str, Any]) -> str:
    if str(snapshot.get("status") or "") == "missing":
        return "\n".join(
            [
                "История сессий пока не найдена.",
                f"State file: {snapshot.get('state_file') or '-'}",
                "Запусти хотя бы один plan или session-run.",
            ]
        )
    last_run = snapshot.get("last_run") if isinstance(snapshot.get("last_run"), dict) else {}
    lines = [
        "Сводка сессий",
        f"Всего отправлено сообщений: {snapshot.get('messages_sent_total') or 0}",
        f"Курсор шаблонов: {snapshot.get('message_cursor') or 0}",
        f"Курсор адресатов: {snapshot.get('message_target_cursor') or 0}",
    ]
    if last_run:
        lines.extend(
            [
                "",
                "Последний запуск",
                f"- {last_run.get('run_id') or '-'} · статус: {last_run.get('status') or '-'}",
                f"- Визитов: {last_run.get('visit_count') or 0} · сообщений: {last_run.get('message_count') or 0} · отправлено: {last_run.get('sent_count') or 0}",
                f"- Адресат: {last_run.get('message_target_username') or 'не выбран'}",
            ]
        )
        unsent = last_run.get("unsent_messages") if isinstance(last_run.get("unsent_messages"), list) else []
        if unsent:
            lines.extend(["", "Неотправленные сообщения"])
            for item in unsent:
                lines.append(
                    f"- #{item.get('index') or 0} · {str(item.get('text') or '').strip()} · sent={int(bool(item.get('sent')))}"
                )
    return "\n".join(lines)


def format_session_history(snapshot: dict[str, Any]) -> str:
    latest_runs = snapshot.get("latest_runs") if isinstance(snapshot.get("latest_runs"), list) else []
    if not latest_runs:
        return "История запусков сессии\nПока нет run.json."
    lines = ["История запусков сессии"]
    for item in latest_runs[-8:]:
        lines.append(
            f"- {item.get('run_id') or '-'} · {item.get('status') or '-'} · визитов {item.get('visit_count') or 0} · сообщений {item.get('message_count') or 0} · отправлено {item.get('sent_count') or 0}"
        )
    return "\n".join(lines)


def format_invite_status_payload(payload: dict[str, Any]) -> str:
    counts = payload.get("counts") if isinstance(payload.get("counts"), dict) else {}
    next_users = payload.get("users") if isinstance(payload.get("users"), list) else []
    latest_runs = payload.get("latest_runs") if isinstance(payload.get("latest_runs"), list) else []
    if next_users and not counts and "total_users" not in payload:
        lines = [
            "Что осталось в очереди",
            f"Папка задачи: {payload.get('job_dir') or '-'}",
            f"Показано username: {payload.get('selected') or len(next_users)}",
        ]
        for item in next_users:
            lines.append(
                f"- {item.get('username') or '-'} · статус: {item.get('status') or '-'} · попыток: {item.get('attempts') or 0}"
            )
        return "\n".join(lines)

    lines = [
        "Добавление контактов из TXT",
        f"Папка задачи: {payload.get('job_dir') or '-'}",
        f"Источник задачи: {payload.get('chat_url') or '-'}",
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


def format_contact_batch_payload(payload: dict[str, Any]) -> str:
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    results = payload.get("results") if isinstance(payload.get("results"), list) else []
    lines = [
        "Добавление контактов из TXT",
        f"Статус: {payload.get('status') or '-'}",
        f"Папка задачи: {payload.get('job_dir') or '-'}",
        f"Файл списка: {payload.get('input_path') or '-'}",
        f"Выбрано username: {payload.get('selected_users') or 0}",
        f"Успешно добавлено: {payload.get('added_count') or 0}",
        f"Ошибок: {payload.get('failed_count') or 0}",
        f"Осталось в очереди: {payload.get('remaining_candidates') or 0}",
    ]
    if summary:
        counts = summary.get("counts") if isinstance(summary.get("counts"), dict) else {}
        lines.extend(["", "Состояние задачи"])
        for key, value in sorted(counts.items()):
            lines.append(f"- {key}: {value}")
    if results:
        lines.extend(["", "Последние результаты"])
        for item in results[-8:]:
            error = str(item.get("error") or "").strip()
            suffix = f" · ошибка: {error}" if error else ""
            lines.append(
                f"- {item.get('username') or '-'} · {item.get('outcome') or item.get('status') or '-'}{suffix}"
            )
    remaining = payload.get("remaining_usernames") if isinstance(payload.get("remaining_usernames"), list) else []
    if remaining:
        lines.extend(["", "Что ещё осталось"])
        for username in remaining[:10]:
            lines.append(f"- {username}")
    run_dir = str(payload.get("run_dir") or "").strip()
    if run_dir:
        lines.extend(["", f"Артефакты batch-запуска: {run_dir}"])
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
    continuous = bool(payload.get("continuous"))
    run_info = payload.get("run") if isinstance(payload.get("run"), dict) else payload
    visits = run_info.get("visits") if isinstance(run_info.get("visits"), list) else []
    messages = run_info.get("messages") if isinstance(run_info.get("messages"), list) else []
    sent_count = int(run_info.get("sent_count", 0) or payload.get("sent_count") or 0)
    lines = [
        "Сессия и сообщения",
        f"Статус: {payload.get('status') or run_info.get('status') or 'ok'}",
        f"Режим: {'до ручного Стопа' if continuous else 'один запуск'}",
        f"Запуск: {payload.get('run_dir') or run_info.get('run_dir') or run_info.get('run_id') or '-'}",
        f"Выполнено визитов: {len(visits)}",
        f"Подготовлено сообщений: {len(messages)}",
        f"Отправлено сообщений: {sent_count}",
        f"Адресат сообщений: {run_info.get('message_target_username') or '-'}",
    ]
    if continuous:
        lines.extend(
            [
                f"Полных циклов: {payload.get('cycle_count') or 0}",
                f"Время работы: {payload.get('elapsed_seconds') or 0} сек",
            ]
        )
        cycles = payload.get("cycles") if isinstance(payload.get("cycles"), list) else []
        if cycles:
            lines.extend(["", "Последние циклы"])
            for item in cycles[-5:]:
                lines.append(
                    f"- {item.get('run_id') or '-'} · статус: {item.get('status') or '-'} · визитов: {item.get('visit_count') or 0} · отправлено: {item.get('sent_count') or 0}"
                )
    history = payload.get("history") if isinstance(payload.get("history"), list) else []
    if history:
        lines.extend(["", "История"])
        for item in history[-5:]:
            lines.append(f"- {item}")
    if messages:
        lines.extend(["", "Сообщения"])
        for item in messages[-5:]:
            sent = bool(item.get("sent"))
            lines.append(
                f"- #{item.get('index') or 0} · {'отправлено' if sent else 'не отправлено'} · {str(item.get('text') or '').strip()}"
            )
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

            self.invite_input_path_var = tk.StringVar()
            self.invite_job_dir_var = tk.StringVar()
            self.invite_limit_var = tk.StringVar(value="10")
            self.invite_preview_var = tk.StringVar(value="Список ещё не выбран")

            self.session_config_path_var = tk.StringVar(value=str(DEFAULT_SESSION_CONFIG))
            self.session_new_target_var = tk.StringVar()
            self.session_new_target_label_var = tk.StringVar()
            self.session_new_target_kind_var = tk.StringVar(value="Контакт")
            self.session_auto_send_var = tk.BooleanVar(value=False)
            self.session_continuous_var = tk.BooleanVar(value=True)
            self.session_messages_per_cycle_var = tk.StringVar(value="1")
            self.session_total_limit_var = tk.StringVar(value="0")
            self.session_visit_count_var = tk.StringVar(value="6")
            self.session_view_min_var = tk.StringVar(value="3")
            self.session_view_max_var = tk.StringVar(value="6")
            self.session_timer_var = tk.StringVar(value="00:00:00")
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
            self._session_timer_started_at: float | None = None
            self._session_timer_after_id: str | None = None
            self._monitor_after_ids: dict[str, str | None] = {
                "telegram_invite_manager": None,
                "telegram_session_runner": None,
            }

            self.profile_combo: ttk.Combobox | None = None
            self.profile_details: tk.Text | None = None
            self.profile_overview: tk.Text | None = None
            self.profile_manager_window: tk.Toplevel | None = None
            self.invite_output: tk.Text | None = None
            self.invite_summary_text: tk.Text | None = None
            self.invite_queue_text: tk.Text | None = None
            self.invite_added_text: tk.Text | None = None
            self.invite_failed_text: tk.Text | None = None
            self.invite_history_text: tk.Text | None = None
            self.session_output: tk.Text | None = None
            self.session_summary_text: tk.Text | None = None
            self.session_history_text: tk.Text | None = None
            self.session_targets_list: tk.Listbox | None = None
            self.session_templates_text: tk.Text | None = None
            self._tool_buttons: dict[str, tk.Button] = {}
            self._tool_frames: dict[str, ttk.Frame] = {}

            self.invite_input_path_var.trace_add("write", self._sync_contact_job_dir)

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

        def _format_elapsed(self, seconds_total: int) -> str:
            total = max(0, int(seconds_total))
            hours, remainder = divmod(total, 3600)
            minutes, seconds = divmod(remainder, 60)
            return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

        def _set_session_templates(self, templates: list[str]) -> None:
            if self.session_templates_text is None:
                return
            self.session_templates_text.delete("1.0", tk.END)
            if templates:
                self.session_templates_text.insert("1.0", "\n".join(str(item) for item in templates))

        def _session_templates(self) -> list[str]:
            if self.session_templates_text is None:
                return []
            return [
                line.strip()
                for line in self.session_templates_text.get("1.0", tk.END).splitlines()
                if line.strip()
            ]

        def _update_session_timer(self) -> None:
            if self._session_timer_started_at is None:
                self.session_timer_var.set("00:00:00")
                self._session_timer_after_id = None
                return
            elapsed = int(time.monotonic() - self._session_timer_started_at)
            self.session_timer_var.set(self._format_elapsed(elapsed))
            self._session_timer_after_id = self.after(1000, self._update_session_timer)

        def _start_session_timer(self) -> None:
            self._stop_session_timer(reset=False)
            self._session_timer_started_at = time.monotonic()
            self.session_timer_var.set("00:00:00")
            self._update_session_timer()

        def _stop_session_timer(self, *, reset: bool = False) -> None:
            if self._session_timer_after_id is not None:
                try:
                    self.after_cancel(self._session_timer_after_id)
                except tk.TclError:
                    pass
                self._session_timer_after_id = None
            self._session_timer_started_at = None
            if reset:
                self.session_timer_var.set("00:00:00")

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

        def _cancel_tool_monitor(self, tool_id: str) -> None:
            after_id = self._monitor_after_ids.get(tool_id)
            if after_id:
                try:
                    self.after_cancel(after_id)
                except tk.TclError:
                    pass
            self._monitor_after_ids[tool_id] = None

        def _schedule_tool_monitor(self, tool_id: str) -> None:
            self._cancel_tool_monitor(tool_id)
            self._poll_tool_snapshot(tool_id)

        def _poll_tool_snapshot(self, tool_id: str) -> None:
            try:
                if tool_id == "telegram_invite_manager":
                    self._refresh_invite_dashboard()
                elif tool_id == "telegram_session_runner":
                    self._refresh_session_dashboard()
            except Exception as exc:
                self._log_event(tool_id, f"Не удалось обновить live-статус: {exc}")
            with self._process_lock:
                proc = self._active_processes.get(tool_id)
                running = proc is not None and proc.poll() is None
            if running:
                self._monitor_after_ids[tool_id] = self.after(
                    1800,
                    lambda current=tool_id: self._poll_tool_snapshot(current),
                )
            else:
                self._monitor_after_ids[tool_id] = None

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
            monitor_active_state: bool = False,
        ) -> None:
            with self._process_lock:
                existing = self._active_processes.get(tool_id)
                if existing is not None and existing.poll() is None:
                    messagebox.showinfo("Панель Telegram", "Сначала дождись завершения текущего действия или нажми `Стоп`.")
                    return

            command_text = shlex.join(command.argv)
            if tool_id == "telegram_session_runner" and action_label == "запуск session runner":
                self._start_session_timer()
            if monitor_active_state:
                self._schedule_tool_monitor(tool_id)
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
            self._cancel_tool_monitor(tool_id)
            if tool_id == "telegram_session_runner" and action_label == "запуск session runner":
                self._stop_session_timer()
            if stopped:
                self._status_var_for_tool(tool_id).set("Остановлено")
                self._log_event(tool_id, f"Остановлено: {action_label}")
                if tool_id == "telegram_invite_manager":
                    self._refresh_invite_dashboard()
                elif tool_id == "telegram_session_runner":
                    self._refresh_session_dashboard()
                return
            if error_text:
                self._status_var_for_tool(tool_id).set("Ошибка")
                self._log_event(tool_id, f"Ошибка: {action_label}")
                self._log_event(tool_id, error_text)
                if tool_id == "telegram_invite_manager":
                    self._refresh_invite_dashboard()
                elif tool_id == "telegram_session_runner":
                    self._refresh_session_dashboard()
                messagebox.showerror("Панель Telegram", error_text)
                return
            assert payload is not None
            payload_status = str(payload.get("status") or "").strip().lower()
            if payload_status == "stopped":
                self._status_var_for_tool(tool_id).set("Остановлено")
            elif payload_status == "completed_with_errors":
                self._status_var_for_tool(tool_id).set("Есть ошибки")
            elif payload_status == "dry_run":
                self._status_var_for_tool(tool_id).set("Проверка завершена")
            else:
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
            ttk.Label(body, text="Все найденные профили", style="Field.TLabel").grid(
                row=6, column=0, sticky="w", pady=(14, 0)
            )
            self.profile_overview = self._create_readonly_text(body, height=4)
            self.profile_overview.grid(row=7, column=0, columnspan=4, sticky="nsew", pady=(6, 0))

        def _build_tool_selector(self, parent: ttk.Frame) -> None:
            body = self._create_card(
                parent,
                "2. Выбор инструмента",
                "Нажми нужную кнопку старта. Ниже откроется только один рабочий экран, чтобы не путаться.",
            )
            selector = ttk.Frame(body, style="Card.TFrame")
            selector.pack(fill="x")

            tools = [
                ("telegram_invite_manager", "Добавить контакты из TXT"),
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
                text="`Добавить контакты из TXT` открывает простой режим реального добавления username в контакты выбранного сверху профиля. `Старт сессии` открывает random walk и список адресатов сообщений.",
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
                "Инструмент: Добавление контактов из TXT",
                "Загрузи файл с username и запусти реальное добавление этих людей в контакты выбранного сверху Telegram-пользователя. Ниже сразу видны очередь, успешно добавленные, ошибки и история запусков.",
                expand=True,
            )
            body.columnconfigure(0, weight=1)
            body.columnconfigure(1, weight=1)
            body.columnconfigure(2, weight=1)

            top_buttons = ttk.Frame(body, style="Card.TFrame")
            top_buttons.grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 12))
            invite_start_button = ttk.Button(
                top_buttons,
                text="Старт добавления",
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
                text="Что осталось",
                command=self._invite_show_next,
            )
            invite_next_button.pack(side=tk.LEFT, padx=(10, 0))
            self._register_busy_widget("telegram_invite_manager", invite_next_button)
            invite_continue_button = ttk.Button(
                top_buttons,
                text="Продолжить очередь",
                command=self._invite_continue_queue,
            )
            invite_continue_button.pack(side=tk.LEFT, padx=(10, 0))
            self._register_busy_widget("telegram_invite_manager", invite_continue_button)
            invite_retry_button = ttk.Button(
                top_buttons,
                text="Повторить ошибки",
                command=self._invite_retry_failed,
            )
            invite_retry_button.pack(side=tk.LEFT, padx=(10, 0))
            self._register_busy_widget("telegram_invite_manager", invite_retry_button)
            invite_refresh_button = ttk.Button(
                top_buttons,
                text="Обновить экран",
                command=self._refresh_invite_dashboard,
            )
            invite_refresh_button.pack(side=tk.LEFT, padx=(10, 0))
            self._register_busy_widget("telegram_invite_manager", invite_refresh_button)
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

            ttk.Label(body, text="Шаг 1. Файл со списком username с компьютера", style="Field.TLabel").grid(
                row=1, column=0, sticky="w"
            )
            file_row = ttk.Frame(body, style="Card.TFrame")
            file_row.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(4, 10))
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
            ttk.Label(body, textvariable=self.invite_preview_var, style="CardSubtitle.TLabel").grid(
                row=3, column=0, columnspan=3, sticky="w"
            )

            ttk.Label(body, text="Шаг 2. Папка задачи", style="Field.TLabel").grid(
                row=4, column=0, sticky="w", pady=(8, 0)
            )
            ttk.Entry(body, textvariable=self.invite_job_dir_var).grid(
                row=5, column=0, columnspan=3, sticky="ew", pady=(4, 10)
            )

            ttk.Label(
                body,
                text="Поддерживаются .txt, .csv и .json. Для .txt одна строка = один @username, consent=yes ставится автоматически. Контакты будет добавлять именно тот профиль, который выбран сверху.",
                style="CardSubtitle.TLabel",
            ).grid(row=6, column=0, columnspan=3, sticky="w")

            next_row = ttk.Frame(body, style="Card.TFrame")
            next_row.grid(row=7, column=0, columnspan=3, sticky="w", pady=(14, 0))
            ttk.Label(next_row, text="Сколько username обработать за запуск", style="Field.TLabel").pack(
                side=tk.LEFT
            )
            ttk.Entry(next_row, textvariable=self.invite_limit_var, width=8).pack(
                side=tk.LEFT, padx=(10, 0)
            )

            summary_panel = self._create_inline_panel(
                body,
                "Текущее состояние задачи",
                "Здесь сразу видны общая сводка, сколько осталось и что происходило в последнем batch.",
            )
            summary_panel.grid(row=8, column=0, sticky="nsew", padx=(0, 10), pady=(14, 0))
            summary_panel.columnconfigure(0, weight=1)
            self.invite_summary_text = self._create_readonly_text(summary_panel, height=10)
            self.invite_summary_text.grid(row=2, column=0, sticky="nsew")
            self._bind_scroll_to_widget(self.invite_summary_text)

            history_panel = self._create_inline_panel(
                body,
                "История запусков",
                "Каждая строка показывает execution_id, статус, сколько удалось добавить и сколько осталось.",
            )
            history_panel.grid(row=8, column=1, sticky="nsew", padx=(0, 10), pady=(14, 0))
            history_panel.columnconfigure(0, weight=1)
            self.invite_history_text = self._create_readonly_text(history_panel, height=10)
            self.invite_history_text.grid(row=2, column=0, sticky="nsew")
            self._bind_scroll_to_widget(self.invite_history_text)

            errors_panel = self._create_inline_panel(
                body,
                "Последние ошибки",
                "Если что-то не сработало, ошибка будет здесь. Кнопка `Повторить ошибки` берёт именно этих пользователей со статусом failed.",
            )
            errors_panel.grid(row=8, column=2, sticky="nsew", pady=(14, 0))
            errors_panel.columnconfigure(0, weight=1)
            self.invite_failed_text = self._create_readonly_text(errors_panel, height=10)
            self.invite_failed_text.grid(row=2, column=0, sticky="nsew")
            self._bind_scroll_to_widget(self.invite_failed_text)

            queue_panel = self._create_inline_panel(
                body,
                "Осталось в очереди",
                "Это ближайшие username, которые ещё не обработаны.",
            )
            queue_panel.grid(row=9, column=0, sticky="nsew", padx=(0, 10), pady=(14, 0))
            queue_panel.columnconfigure(0, weight=1)
            self.invite_queue_text = self._create_readonly_text(queue_panel, height=10)
            self.invite_queue_text.grid(row=2, column=0, sticky="nsew")
            self._bind_scroll_to_widget(self.invite_queue_text)

            added_panel = self._create_inline_panel(
                body,
                "Уже добавлены",
                "Последние успешно добавленные контакты из этой задачи.",
            )
            added_panel.grid(row=9, column=1, sticky="nsew", padx=(0, 10), pady=(14, 0))
            added_panel.columnconfigure(0, weight=1)
            self.invite_added_text = self._create_readonly_text(added_panel, height=10)
            self.invite_added_text.grid(row=2, column=0, sticky="nsew")
            self._bind_scroll_to_widget(self.invite_added_text)

            ttk.Label(body, text="Живой статус и лог", style="Field.TLabel").grid(
                row=10, column=0, sticky="w", pady=(16, 0)
            )
            self.invite_output = self._create_readonly_text(body, height=14)
            self.invite_output.grid(row=11, column=0, columnspan=3, sticky="nsew", pady=(6, 0))
            self._bind_scroll_to_widget(self.invite_output)
            body.rowconfigure(11, weight=1)

        def _build_session_view(self, parent: ttk.Frame) -> None:
            body = self._create_card(
                parent,
                "Инструмент: Сессия и сообщения",
                "Этот экран отдельно управляет живой Telegram-сессией: random walk по открытому профилю, список адресатов, текст сообщения, интервалы и история запусков.",
                expand=True,
            )
            body.columnconfigure(0, weight=1)
            body.columnconfigure(1, weight=1)

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
            session_refresh_button = ttk.Button(
                top_buttons,
                text="Обновить экран",
                command=self._refresh_session_dashboard,
            )
            session_refresh_button.pack(side=tk.LEFT, padx=(10, 0))
            self._register_busy_widget("telegram_session_runner", session_refresh_button)
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
            ttk.Label(
                top_buttons,
                text="Таймер:",
                style="Field.TLabel",
            ).pack(side=tk.LEFT, padx=(20, 6))
            ttk.Label(
                top_buttons,
                textvariable=self.session_timer_var,
                style="CardSubtitle.TLabel",
            ).pack(side=tk.LEFT)

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
            recipients_row.columnconfigure(1, weight=1)

            recipients_panel = self._create_inline_panel(
                recipients_row,
                "Кому писать",
                "Список справа не нужен: выбери адресатов здесь или загрузи их из конфига.",
            )
            recipients_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
            recipients_panel.columnconfigure(0, weight=1)
            recipients_panel.rowconfigure(2, weight=1)

            self.session_targets_list = self._create_listbox(
                recipients_panel,
                selectmode=tk.EXTENDED,
                height=10,
            )
            self.session_targets_list.grid(row=2, column=0, sticky="nsew", pady=(0, 10))
            self._bind_scroll_to_widget(self.session_targets_list)
            session_remove_target_button = ttk.Button(
                recipients_panel,
                text="Удалить выбранных",
                command=self._remove_session_targets,
            )
            session_remove_target_button.grid(row=3, column=0, sticky="ew")
            self._register_busy_widget("telegram_session_runner", session_remove_target_button)

            ttk.Label(recipients_panel, text="Добавить новый адресат", style="Field.TLabel").grid(
                row=4, column=0, sticky="w", pady=(12, 0)
            )
            ttk.Label(recipients_panel, text="Username или @ссылка", style="Field.TLabel").grid(
                row=5, column=0, sticky="w", pady=(8, 0)
            )
            ttk.Entry(recipients_panel, textvariable=self.session_new_target_var).grid(
                row=6, column=0, sticky="ew", pady=(4, 0)
            )
            ttk.Label(recipients_panel, text="Понятное название", style="Field.TLabel").grid(
                row=7, column=0, sticky="w", pady=(8, 0)
            )
            ttk.Entry(recipients_panel, textvariable=self.session_new_target_label_var).grid(
                row=8, column=0, sticky="ew", pady=(4, 0)
            )
            ttk.Label(recipients_panel, text="Тип адресата", style="Field.TLabel").grid(
                row=9, column=0, sticky="w", pady=(8, 0)
            )
            kind_combo = ttk.Combobox(
                recipients_panel,
                textvariable=self.session_new_target_kind_var,
                state="readonly",
                values=["Контакт", "Группа"],
            )
            kind_combo.grid(row=10, column=0, sticky="ew", pady=(4, 0))
            session_add_target_button = ttk.Button(
                recipients_panel,
                text="Добавить адресата",
                command=self._add_session_target,
            )
            session_add_target_button.grid(row=11, column=0, sticky="ew", pady=(10, 0))
            self._register_busy_widget("telegram_session_runner", session_add_target_button)

            ttk.Label(
                recipients_panel,
                text="Введи @username, при желании дай понятное имя и выбери тип адресата.",
                style="CardSubtitle.TLabel",
            ).grid(row=12, column=0, sticky="w", pady=(10, 0))

            settings_panel = self._create_inline_panel(
                recipients_row,
                "Как писать",
                "Здесь задаётся режим самой сессии: длительность визитов, количество сообщений и непрерывная работа до нажатия `Стоп`.",
            )
            settings_panel.grid(row=0, column=1, sticky="nsew")
            settings_panel.columnconfigure(1, weight=1)

            ttk.Label(settings_panel, text="Визитов за один цикл", style="Field.TLabel").grid(
                row=2, column=0, sticky="w"
            )
            ttk.Entry(settings_panel, textvariable=self.session_visit_count_var, width=10).grid(
                row=2, column=1, sticky="w", padx=(12, 0)
            )
            ttk.Label(
                settings_panel,
                text="Сколько случайных переходов по чатам сделать за один цикл сессии.",
                style="CardSubtitle.TLabel",
            ).grid(row=3, column=0, columnspan=2, sticky="w", pady=(4, 10))

            ttk.Label(settings_panel, text="Минимум секунд в чате", style="Field.TLabel").grid(
                row=4, column=0, sticky="w"
            )
            ttk.Entry(settings_panel, textvariable=self.session_view_min_var, width=10).grid(
                row=4, column=1, sticky="w", padx=(12, 0)
            )
            ttk.Label(
                settings_panel,
                text="Минимальная случайная пауза, сколько пользователь находится в открытом чате.",
                style="CardSubtitle.TLabel",
            ).grid(row=5, column=0, columnspan=2, sticky="w", pady=(4, 10))

            ttk.Label(settings_panel, text="Максимум секунд в чате", style="Field.TLabel").grid(
                row=6, column=0, sticky="w"
            )
            ttk.Entry(settings_panel, textvariable=self.session_view_max_var, width=10).grid(
                row=6, column=1, sticky="w", padx=(12, 0)
            )
            ttk.Label(
                settings_panel,
                text="Максимальная случайная пауза в одном чате.",
                style="CardSubtitle.TLabel",
            ).grid(row=7, column=0, columnspan=2, sticky="w", pady=(4, 10))

            ttk.Label(settings_panel, text="Сообщений за один цикл", style="Field.TLabel").grid(
                row=8, column=0, sticky="w"
            )
            ttk.Entry(settings_panel, textvariable=self.session_messages_per_cycle_var, width=10).grid(
                row=8, column=1, sticky="w", padx=(12, 0)
            )
            ttk.Label(
                settings_panel,
                text="Сколько сообщений пытаться отправить за один проход по сессии.",
                style="CardSubtitle.TLabel",
            ).grid(row=9, column=0, columnspan=2, sticky="w", pady=(4, 10))

            ttk.Label(settings_panel, text="Максимум отправить за всю сессию", style="Field.TLabel").grid(
                row=10, column=0, sticky="w"
            )
            ttk.Entry(settings_panel, textvariable=self.session_total_limit_var, width=10).grid(
                row=10, column=1, sticky="w", padx=(12, 0)
            )
            ttk.Label(
                settings_panel,
                text="Поставь `0`, если лимит не нужен и сессия должна слать сообщения до ручного `Стоп`.",
                style="CardSubtitle.TLabel",
            ).grid(row=11, column=0, columnspan=2, sticky="w", pady=(4, 10))

            ttk.Checkbutton(
                settings_panel,
                text="Отправлять сообщения сразу, а не оставлять в строке ввода",
                variable=self.session_auto_send_var,
            ).grid(row=12, column=0, columnspan=2, sticky="w")
            ttk.Checkbutton(
                settings_panel,
                text="Крутить сессию непрерывно до нажатия `Стоп`",
                variable=self.session_continuous_var,
            ).grid(row=13, column=0, columnspan=2, sticky="w", pady=(8, 0))

            ttk.Label(
                body,
                text="Текущий профиль сверху будет автоматически подставлен в runtime-config перед запуском.",
                style="CardSubtitle.TLabel",
            ).grid(row=5, column=0, columnspan=2, sticky="w", pady=(12, 0))

            templates_panel = self._create_inline_panel(
                body,
                "Шаг 3. Текст сообщения",
                "Одна строка = один шаблон. Если строк несколько, session runner будет их ротировать между циклами.",
            )
            templates_panel.grid(row=6, column=0, columnspan=2, sticky="nsew", pady=(12, 0))
            templates_panel.columnconfigure(0, weight=1)
            self.session_templates_text = tk.Text(
                templates_panel,
                wrap="word",
                height=6,
                bg=self._colors["field"],
                fg=self._colors["text"],
                insertbackground=self._colors["text"],
                highlightbackground=self._colors["border"],
                highlightcolor=self._colors["accent"],
                highlightthickness=1,
                relief="flat",
                borderwidth=0,
                padx=12,
                pady=10,
                font=self._fonts["base"],
            )
            self.session_templates_text.grid(row=2, column=0, sticky="nsew")
            self._bind_scroll_to_widget(self.session_templates_text)

            summary_panel = self._create_inline_panel(
                body,
                "Сводка и подтверждение отправки",
                "Здесь видно общий прогресс, последний запуск и сообщения, которые не были отправлены.",
            )
            summary_panel.grid(row=7, column=0, sticky="nsew", pady=(14, 0), padx=(0, 10))
            summary_panel.columnconfigure(0, weight=1)
            self.session_summary_text = self._create_readonly_text(summary_panel, height=10)
            self.session_summary_text.grid(row=2, column=0, sticky="nsew")
            self._bind_scroll_to_widget(self.session_summary_text)

            history_panel = self._create_inline_panel(
                body,
                "История запусков сессии",
                "Показывает последние run.json: статус, визиты, сколько сообщений действительно отправлено.",
            )
            history_panel.grid(row=7, column=1, sticky="nsew", pady=(14, 0))
            history_panel.columnconfigure(0, weight=1)
            self.session_history_text = self._create_readonly_text(history_panel, height=10)
            self.session_history_text.grid(row=2, column=0, sticky="nsew")
            self._bind_scroll_to_widget(self.session_history_text)

            ttk.Label(body, text="Живой статус и лог", style="Field.TLabel").grid(
                row=8, column=0, sticky="w", pady=(16, 0)
            )
            self.session_output = self._create_readonly_text(body, height=16)
            self.session_output.grid(row=9, column=0, columnspan=2, sticky="nsew", pady=(6, 0))
            self._bind_scroll_to_widget(self.session_output)
            body.rowconfigure(9, weight=1)

        def _refresh_summary(self) -> None:
            selected_profile = self._selected_profile()
            profile_part = (
                format_profile_label(selected_profile) if selected_profile is not None else "профиль не выбран"
            )
            active_label = (
                "Добавление контактов из TXT"
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
                self._set_readonly_text(self.profile_overview, "Профили пока не найдены.")
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
            self._set_readonly_text(self.profile_overview, format_profiles_overview(self._profiles))
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
                if self.invite_input_path_var.get().strip() and not self.invite_job_dir_var.get().strip():
                    self._sync_contact_job_dir()
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

        def _sync_contact_job_dir(self, *_args: object) -> None:
            input_path = self.invite_input_path_var.get().strip()
            if not input_path or self.invite_job_dir_var.get().strip():
                return
            profile = self._selected_profile()
            profile_name = str((profile or {}).get("profile_name") or "profile").strip() or "profile"
            self.invite_job_dir_var.set(
                str(
                    default_contact_add_job_dir(
                        profile_name=profile_name,
                        input_path=input_path,
                        output_root=DEFAULT_INVITE_OUTPUT_ROOT,
                    )
                )
            )

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
                            "Добавление контактов из TXT",
                            "1. Сверху выбери Telegram-профиль, который будет добавлять контакты.",
                            "2. Нажми `Загрузить TXT / CSV / JSON` и выбери файл с компьютера.",
                            "3. Нажми `Старт добавления`.",
                        ]
                    ),
                )
                self._refresh_invite_dashboard()
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
                self._refresh_session_dashboard()
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
                self.invite_job_dir_var.set("")
                self._sync_contact_job_dir()
                self.invite_status_var.set("Файл списка выбран")
                self._log_event("telegram_invite_manager", f"Выбран файл списка: {selected}")
                self._refresh_invite_dashboard()

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

        def _refresh_invite_dashboard(self) -> None:
            job_dir_text = self.invite_job_dir_var.get().strip()
            if not job_dir_text:
                preview_path = self.invite_input_path_var.get().strip()
                if preview_path:
                    try:
                        preview = preview_invite_input_file(preview_path)
                    except Exception as exc:
                        self._set_readonly_text(
                            self.invite_summary_text,
                            f"Не удалось прочитать список username:\n{exc}",
                        )
                        return
                    self.invite_preview_var.set(
                        f"Уникальных username: {preview.get('unique_usernames') or 0} · дубликатов: {preview.get('duplicates') or 0} · ошибок: {preview.get('invalid_count') or 0}"
                    )
                    self._set_readonly_text(self.invite_summary_text, format_invite_input_preview(preview))
                    self._set_readonly_text(
                        self.invite_queue_text,
                        _format_username_block(
                            "Первые username из файла",
                            list(preview.get("usernames") or []),
                            empty_text="В файле пока нет корректных username.",
                        ),
                    )
                    self._set_readonly_text(self.invite_added_text, "Уже добавлены\nЗадача ещё не запускалась.")
                    self._set_readonly_text(self.invite_failed_text, "Последние ошибки\nОшибок пока нет.")
                    self._set_readonly_text(self.invite_history_text, "История batch-запусков\nПока нет запусков.")
                return

            snapshot = contact_job_snapshot(job_dir_text)
            self._set_readonly_text(self.invite_summary_text, format_contact_dashboard_snapshot(snapshot))
            self._set_readonly_text(
                self.invite_queue_text,
                _format_username_block(
                    "Осталось в очереди",
                    list(snapshot.get("pending_usernames") or []),
                    empty_text="Очередь сейчас пуста.",
                ),
            )
            self._set_readonly_text(
                self.invite_added_text,
                _format_username_block(
                    "Уже добавлены",
                    list(snapshot.get("added_usernames") or []),
                    empty_text="Пока никто не добавлен.",
                ),
            )
            self._set_readonly_text(self.invite_failed_text, format_contact_errors(snapshot))
            self._set_readonly_text(self.invite_history_text, format_contact_history(snapshot))
            self.invite_preview_var.set(
                f"Осталось: {snapshot.get('pending_total') or 0} · добавлено: {snapshot.get('added_total') or 0} · ошибок: {snapshot.get('failed_total') or 0}"
            )

        def _refresh_session_dashboard(self) -> None:
            snapshot = session_history_snapshot(
                state_file=DEFAULT_SESSION_STATE_FILE,
                runs_dir=DEFAULT_SESSION_RUNS_DIR,
            )
            self._set_readonly_text(self.session_summary_text, format_session_dashboard_snapshot(snapshot))
            self._set_readonly_text(self.session_history_text, format_session_history(snapshot))

        def _invite_batch_command(
            self,
            *,
            input_path: str | Path | None,
            statuses: list[str] | tuple[str, ...] | None,
            action_label: str,
        ) -> None:
            selected_profile = self._selected_profile()
            if selected_profile is None:
                messagebox.showinfo("Панель Telegram", "Сначала выбери Telegram-профиль сверху.")
                return
            try:
                limit = max(int(self.invite_limit_var.get() or "0"), 0)
            except ValueError:
                limit = 0
            try:
                command = contact_add_batch_command(
                    input_path=input_path,
                    job_dir=self._invite_resolved_job_dir(),
                    profile_name=str(selected_profile.get("profile_name") or ""),
                    portable_profile_dir=str(selected_profile.get("profile_dir") or ""),
                    account_username=str((selected_profile.get("account") or {}).get("username") or ""),
                    account_label=str((selected_profile.get("account") or {}).get("label") or ""),
                    limit=limit,
                    statuses=statuses,
                )
            except Exception as exc:
                messagebox.showerror("Панель Telegram", f"Не удалось подготовить batch-добавление контактов:\n{exc}")
                return
            self._start_json_command(
                tool_id="telegram_invite_manager",
                action_label=action_label,
                command=command,
                on_success=self._on_invite_init_success,
                monitor_active_state=True,
            )

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
            input_path = self.invite_input_path_var.get().strip()
            if not input_path:
                raise ValueError("Выбери файл со списком username.")
            profile = self._selected_profile()
            profile_name = str((profile or {}).get("profile_name") or "profile").strip() or "profile"
            resolved = default_contact_add_job_dir(
                profile_name=profile_name,
                input_path=input_path,
                output_root=DEFAULT_INVITE_OUTPUT_ROOT,
            )
            self.invite_job_dir_var.set(str(resolved))
            return resolved

        def _invite_create_job(self) -> None:
            input_path = self.invite_input_path_var.get().strip()
            if not input_path:
                messagebox.showinfo("Панель Telegram", "Выбери файл со списком username.")
                return
            self._invite_batch_command(
                input_path=input_path,
                statuses=["new", "checked"],
                action_label="добавление контактов из файла",
            )

        def _invite_continue_queue(self) -> None:
            try:
                self._invite_resolved_job_dir()
            except Exception as exc:
                messagebox.showerror("Панель Telegram", f"Не удалось определить папку задачи:\n{exc}")
                return
            self._invite_batch_command(
                input_path=None,
                statuses=["new", "checked"],
                action_label="продолжение очереди добавления контактов",
            )

        def _invite_retry_failed(self) -> None:
            try:
                self._invite_resolved_job_dir()
            except Exception as exc:
                messagebox.showerror("Панель Telegram", f"Не удалось определить папку задачи:\n{exc}")
                return
            self._invite_batch_command(
                input_path=None,
                statuses=["failed"],
                action_label="повтор batch ошибок добавления контактов",
            )

        def _invite_show_status(self) -> None:
            try:
                self._refresh_invite_dashboard()
                self._set_readonly_text(
                    self.invite_output,
                    "Статус задачи обновлён из invite_state.json и batch-артефактов.",
                )
            except Exception as exc:
                messagebox.showerror("Панель Telegram", f"Не удалось прочитать статус:\n{exc}")

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
                action_label="чтение оставшихся username",
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
                defaults = session_config_defaults(self.session_config_path_var.get())
            except Exception as exc:
                messagebox.showerror("Панель Telegram", f"Не удалось прочитать конфиг режима сессии:\n{exc}")
                return
            self._session_targets = list(defaults["message_targets"])
            self.session_auto_send_var.set(bool(defaults["auto_send"]))
            self.session_messages_per_cycle_var.set(str(defaults["drafts_per_run"]))
            self.session_total_limit_var.set(str(defaults["total_message_limit"]))
            self.session_visit_count_var.set(str(defaults["random_walk_visits_per_run"]))
            self.session_view_min_var.set(str(defaults["view_min_seconds"]))
            self.session_view_max_var.set(str(defaults["view_max_seconds"]))
            self._set_session_templates(list(defaults["templates"]))
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
                        f"Автоотправка: {'включена' if self.session_auto_send_var.get() else 'выключена'}",
                        f"Визитов за цикл: {self.session_visit_count_var.get()}",
                        f"Интервал в чате: {self.session_view_min_var.get()}-{self.session_view_max_var.get()} сек",
                        f"Сообщений за цикл: {self.session_messages_per_cycle_var.get()}",
                        f"Лимит на всю сессию: {self.session_total_limit_var.get()}",
                        f"Шаблонов текста: {len(defaults['templates'])}",
                    ]
                ),
            )
            self._refresh_session_dashboard()
            if show_feedback:
                messagebox.showinfo(
                    "Панель Telegram",
                    (
                        f"Из конфига загружено адресатов: {len(self._session_targets)}\n"
                        f"Шаблонов текста: {len(defaults['templates'])}"
                    ),
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
            visits_per_cycle = int((self.session_visit_count_var.get() or "0").strip())
            view_min_seconds = int((self.session_view_min_var.get() or "0").strip())
            view_max_seconds = int((self.session_view_max_var.get() or "0").strip())
            drafts_per_run = int((self.session_messages_per_cycle_var.get() or "0").strip())
            total_message_limit = int((self.session_total_limit_var.get() or "0").strip())
            templates = self._session_templates()
            wants_messages = drafts_per_run > 0 and bool(templates)
            if visits_per_cycle <= 0:
                raise ValueError("Количество визитов за цикл должно быть больше нуля.")
            if view_min_seconds <= 0 or view_max_seconds <= 0:
                raise ValueError("Минимум и максимум секунд в чате должны быть больше нуля.")
            if view_min_seconds > view_max_seconds:
                raise ValueError("Минимум секунд в чате не может быть больше максимума.")
            if drafts_per_run < 0:
                raise ValueError("Количество сообщений за цикл не может быть отрицательным.")
            if total_message_limit < 0:
                raise ValueError("Лимит сообщений за всю сессию не может быть отрицательным.")
            if drafts_per_run > 0 and not templates:
                raise ValueError("Добавь хотя бы один текст сообщения или поставь 0 сообщений за цикл.")
            if wants_messages and not self._session_targets:
                raise ValueError("Добавь хотя бы одного адресата для сообщений.")
            selected_profile = self._selected_profile()
            profile_dir = str(selected_profile.get("profile_dir") or "") if selected_profile else ""
            return build_session_runtime_config(
                base_config_path=self.session_config_path_var.get(),
                output_path=self._session_runtime_config_path(),
                message_targets=self._session_targets,
                message_templates=templates,
                drafts_per_run=drafts_per_run,
                total_message_limit=total_message_limit,
                portable_profile_dir=profile_dir,
                auto_send=bool(self.session_auto_send_var.get()),
                session_overrides={
                    "random_walk_visits_per_run": visits_per_cycle,
                    "view_min_seconds": view_min_seconds,
                    "view_max_seconds": view_max_seconds,
                },
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
                    continuous=bool(self.session_continuous_var.get()),
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
                monitor_active_state=True,
            )

        def _on_invite_init_success(self, payload: dict[str, Any]) -> None:
            if payload.get("job_dir"):
                self.invite_job_dir_var.set(str(payload["job_dir"]))
            formatter = (
                format_contact_batch_payload
                if isinstance(payload.get("results"), list)
                else format_invite_status_payload
            )
            self._set_readonly_text(self.invite_output, formatter(payload))
            self._refresh_invite_dashboard()

        def _on_session_plan_success(self, payload: dict[str, Any], runtime_config: Path) -> None:
            summary = format_session_plan_payload(payload)
            summary += f"\n\nRuntime config:\n{runtime_config}"
            self._set_readonly_text(self.session_output, summary)
            self._refresh_session_dashboard()

        def _on_session_run_success(self, payload: dict[str, Any], runtime_config: Path) -> None:
            summary = format_session_run_payload(payload)
            summary += f"\n\nRuntime config:\n{runtime_config}"
            self._set_readonly_text(self.session_output, summary)
            self._refresh_session_dashboard()

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
