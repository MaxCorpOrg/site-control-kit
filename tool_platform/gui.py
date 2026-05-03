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
    DEFAULT_PANEL_STATE_ROOT,
    DEFAULT_SESSION_CONFIG,
    DEFAULT_SESSION_RUNS_DIR,
    DEFAULT_SESSION_STATE_FILE,
    active_profile_conflict,
    build_session_runtime_config,
    combined_step_label,
    combined_contact_add_transition,
    combined_flow_state_path,
    combined_session_transition,
    contact_job_snapshot,
    contact_add_batch_command,
    default_contact_add_job_dir,
    default_combined_flow_state,
    format_session_target_label,
    invite_manager_next_command,
    load_combined_flow_state,
    parse_json_payload,
    parse_combined_step_pattern,
    preview_invite_input_file,
    save_combined_flow_state,
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
                    f" · уже было: {last_run.get('already_present_count') or 0}"
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
            f"- {item.get('execution_id') or '-'} · {item.get('status') or '-'} · добавлено {item.get('added_count') or 0} · уже было {item.get('already_present_count') or 0} · ошибок {item.get('failed_count') or 0} · осталось {item.get('remaining_candidates') or 0}"
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


def format_session_targets_summary(targets: list[dict[str, Any]], *, limit: int = 8) -> str:
    lines = [f"Адресаты для сообщений: {len(targets)}"]
    if not targets:
        lines.append("Список пока пуст. Загрузи адресатов из конфига или добавь их в экране `Сессия и сообщения`.")
        return "\n".join(lines)
    for item in targets[:limit]:
        lines.append(f"- {format_session_target_label(item)}")
    if len(targets) > limit:
        lines.append(f"... и ещё {len(targets) - limit}")
    return "\n".join(lines)


def _safe_preview_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def preview_next_session_target(
    targets: list[dict[str, Any]],
    *,
    message_target_cursor: int,
) -> dict[str, Any] | None:
    normalized = [
        item
        for item in targets
        if isinstance(item, dict) and str(item.get("handle") or item.get("label") or "").strip()
    ]
    if not normalized:
        return None
    cursor = max(0, _safe_preview_int(message_target_cursor))
    index = cursor % len(normalized)
    selected = normalized[index]
    return {
        "index": index + 1,
        "count": len(normalized),
        "label": format_session_target_label(selected),
        "handle": str(selected.get("handle") or "").strip(),
        "kind": str(selected.get("kind") or "").strip(),
    }


def preview_next_session_messages(
    templates: list[str],
    *,
    message_cursor: int,
    messages_sent_total: int,
    messages_per_cycle: int,
    total_message_limit: int,
) -> dict[str, Any]:
    clean_templates = [str(item).strip() for item in templates if str(item).strip()]
    requested_count = max(0, _safe_preview_int(messages_per_cycle))
    cursor = max(0, _safe_preview_int(message_cursor))
    sent_total = max(0, _safe_preview_int(messages_sent_total))
    total_limit_value = max(0, _safe_preview_int(total_message_limit))
    remaining_before_cycle = None if total_limit_value <= 0 else max(0, total_limit_value - sent_total)
    payload: dict[str, Any] = {
        "requested_count": requested_count,
        "count": 0,
        "messages": [],
        "remaining_before_cycle": remaining_before_cycle,
        "remaining_after_cycle": remaining_before_cycle,
        "total_limit": total_limit_value,
        "reason": "",
    }
    if not clean_templates:
        payload["reason"] = "шаблоны сообщений не заданы"
        return payload
    if requested_count <= 0:
        payload["reason"] = "сообщения за цикл = 0"
        return payload
    count = min(requested_count, len(clean_templates))
    if total_limit_value > 0:
        count = min(count, remaining_before_cycle or 0)
        if count <= 0:
            payload["reason"] = "общий лимит сообщений уже исчерпан"
            return payload
    payload["messages"] = [
        {
            "index": index + 1,
            "template_index": ((cursor + index) % len(clean_templates)) + 1,
            "text": clean_templates[(cursor + index) % len(clean_templates)],
        }
        for index in range(count)
    ]
    payload["count"] = len(payload["messages"])
    if remaining_before_cycle is None:
        payload["remaining_after_cycle"] = None
    else:
        payload["remaining_after_cycle"] = max(0, remaining_before_cycle - payload["count"])
    return payload


def _append_message_items(lines: list[str], title: str, items: list[dict[str, Any]]) -> None:
    if not items:
        return
    lines.extend(["", title])
    for item in items[:5]:
        text = str(item.get("text") or "").strip() or "(пусто)"
        send_mode = str(item.get("send_mode") or "").strip()
        suffix = f" · режим {send_mode}" if send_mode else ""
        lines.append(f"- #{_safe_preview_int(item.get('index'))} · {text}{suffix}")


def format_session_operator_summary(
    snapshot: dict[str, Any],
    *,
    session_targets: list[dict[str, Any]],
    session_templates: list[str],
    visits_per_cycle: int,
    view_min_seconds: int,
    view_max_seconds: int,
    messages_per_cycle: int,
    total_message_limit: int,
    auto_send: bool,
    continuous: bool,
) -> str:
    messages_sent_total = _safe_preview_int(snapshot.get("messages_sent_total"))
    next_target = preview_next_session_target(
        session_targets,
        message_target_cursor=_safe_preview_int(snapshot.get("message_target_cursor")),
    )
    next_messages = preview_next_session_messages(
        session_templates,
        message_cursor=_safe_preview_int(snapshot.get("message_cursor")),
        messages_sent_total=messages_sent_total,
        messages_per_cycle=messages_per_cycle,
        total_message_limit=total_message_limit,
    )
    last_run = snapshot.get("last_run") if isinstance(snapshot.get("last_run"), dict) else {}
    limit_text = "без лимита" if _safe_preview_int(total_message_limit) <= 0 else str(_safe_preview_int(total_message_limit))
    send_mode_text = "реальная автоотправка" if auto_send else "черновик в поле ввода"
    run_mode_text = "до ручного Стопа" if continuous else "один цикл за запуск"
    lines = [
        "Что сделает следующий запуск",
        f"Режим: {send_mode_text} · {run_mode_text}",
        f"Визитов за цикл: {max(0, _safe_preview_int(visits_per_cycle))} · время в чате: {max(0, _safe_preview_int(view_min_seconds))}-{max(0, _safe_preview_int(view_max_seconds))} сек",
        f"Сообщений за цикл: {max(0, _safe_preview_int(messages_per_cycle))} · общий лимит: {limit_text}",
        f"Следующий адресат: {next_target.get('label') if next_target else 'не выбран'}",
    ]
    if next_messages["count"]:
        lines.extend(["", "Следующие тексты"])
        for item in list(next_messages.get("messages") or []):
            lines.append(f"- #{item.get('index') or 0} · {str(item.get('text') or '').strip()}")
        remaining_after_cycle = next_messages.get("remaining_after_cycle")
        if remaining_after_cycle is None:
            lines.append("После этого цикла общий лимит всё ещё не ограничен.")
        elif _safe_preview_int(remaining_after_cycle) <= 0:
            lines.append("После этого цикла общий лимит будет исчерпан.")
        else:
            lines.append(f"После этого цикла останется по лимиту: {_safe_preview_int(remaining_after_cycle)}")
    else:
        lines.append(f"Следующие тексты: {next_messages.get('reason') or 'в этом цикле сообщений не будет'}")

    lines.extend(
        [
            "",
            "Общий прогресс",
            f"Всего уже отправлено: {messages_sent_total}",
            f"Курсор шаблонов: {_safe_preview_int(snapshot.get('message_cursor'))}",
            f"Курсор адресатов: {_safe_preview_int(snapshot.get('message_target_cursor'))}",
        ]
    )
    if str(snapshot.get("status") or "") == "missing":
        lines.append("История запусков пока не найдена: первый session-run ещё не сохранён.")
        return "\n".join(lines)

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
        sent_messages = last_run.get("sent_messages") if isinstance(last_run.get("sent_messages"), list) else []
        unsent_messages = last_run.get("unsent_messages") if isinstance(last_run.get("unsent_messages"), list) else []
        _append_message_items(lines, "Последние реально отправленные", sent_messages)
        _append_message_items(lines, "Неотправленные / оставшиеся в строке ввода", unsent_messages)
    return "\n".join(lines)


def combined_phase_label(phase: str) -> str:
    mapping = {
        "contact_add": "Шаг 1: добавление контактов",
        "review": "Добавление завершилось с ошибками",
        "session_ready": "Шаг 2 готов: можно запускать сессию",
        "session_running": "Шаг 2 выполняется: сессия работает",
        "stopped": "Остановлено / завершено",
    }
    return mapping.get(str(phase or "").strip(), "Неизвестная фаза")


def format_combined_flow_state(
    state: dict[str, Any],
    *,
    profile_label: str,
    session_targets: list[dict[str, Any]],
    session_templates: list[str],
    visits_per_cycle: int,
    view_min_seconds: int,
    view_max_seconds: int,
    messages_per_cycle: int,
    total_message_limit: int,
    auto_send: bool,
    continuous: bool,
    invite_snapshot: dict[str, Any] | None = None,
    session_snapshot: dict[str, Any] | None = None,
) -> str:
    phase = str(state.get("phase") or "contact_add")
    next_target = preview_next_session_target(
        session_targets,
        message_target_cursor=_safe_preview_int((session_snapshot or {}).get("message_target_cursor")),
    )
    next_messages = preview_next_session_messages(
        session_templates,
        message_cursor=_safe_preview_int((session_snapshot or {}).get("message_cursor")),
        messages_sent_total=_safe_preview_int((session_snapshot or {}).get("messages_sent_total")),
        messages_per_cycle=messages_per_cycle,
        total_message_limit=total_message_limit,
    )
    pattern_tokens = parse_combined_step_pattern(str(state.get("step_pattern") or ""))
    pattern_preview = "".join(pattern_tokens) if pattern_tokens else "12"
    next_step_label = combined_step_label(str(pattern_tokens[_safe_preview_int(state.get("step_cursor")) % len(pattern_tokens)])) if pattern_tokens else combined_step_label("1")
    pending_usernames = (
        list(invite_snapshot.get("pending_usernames") or [])
        if isinstance(invite_snapshot, dict)
        else []
    )
    next_username = str(pending_usernames[0] or "").strip() if pending_usernames else ""
    limit_text = "без лимита" if _safe_preview_int(total_message_limit) <= 0 else str(_safe_preview_int(total_message_limit))
    lines = [
        "Совместный режим `Добавить → Сессия`",
        f"Профиль: {profile_label}",
        f"Фаза: {combined_phase_label(phase)}",
        f"Последнее действие: {state.get('last_action') or 'ещё не запускалось'}",
        f"Последний статус: {state.get('last_status') or '-'}",
        "",
        "Что произойдёт дальше",
        f"Шаблон шагов: {pattern_preview}",
        f"Следующий шаг по шаблону: {next_step_label}",
        f"Следующий username в очереди: {next_username or 'очередь сейчас пуста'}",
        f"Следующий цикл сессии: {max(0, _safe_preview_int(visits_per_cycle))} визитов, {max(0, _safe_preview_int(view_min_seconds))}-{max(0, _safe_preview_int(view_max_seconds))} сек в чате",
        f"Сообщений за цикл: {max(0, _safe_preview_int(messages_per_cycle))} · общий лимит: {limit_text}",
        f"Режим отправки: {'автоотправка' if auto_send else 'черновик'} · {'до ручного Стопа' if continuous else 'один цикл за запуск'}",
        f"Следующий адресат для сообщения: {next_target.get('label') if next_target else 'не выбран'}",
    ]
    if next_messages["count"]:
        lines.append("Следующие тексты для сессии:")
        for item in list(next_messages.get("messages") or []):
            lines.append(f"- #{item.get('index') or 0} · {str(item.get('text') or '').strip()}")
    else:
        lines.append(f"Следующие тексты для сессии: {next_messages.get('reason') or 'в этом цикле сообщений не будет'}")
    lines.extend(
        [
            "",
            f"Файл контактов: {state.get('input_path') or 'не выбран'}",
            f"Папка задачи: {state.get('invite_job_dir') or 'не задана'}",
        ]
    )
    if state.get("last_session_run_dir"):
        lines.append(f"Последний session run: {state.get('last_session_run_dir')}")
    last_action = str(state.get("last_action") or "").strip()
    if phase == "contact_add":
        if last_action == "combined_session_finished_next_contact":
            lines.append("Что дальше: система сама запускает следующий шаг добавления.")
        else:
            lines.append("Что дальше: выбери файл контактов и нажми `Старт совместного режима`.")
    elif phase == "review":
        lines.append("Что дальше: посмотри ошибки ниже и перезапусти общий режим, если хочешь повторить цикл.")
    elif phase == "session_ready":
        if last_action == "combined_contact_add_finished_auto":
            lines.append("Что дальше: система сама запускает шаг сессии.")
        else:
            lines.append("Что дальше: система готова к шагу сессии; если шаг был остановлен, нажми `Старт совместного режима`.")
    elif phase == "session_running":
        lines.append("Что дальше: наблюдай лог ниже или нажми `Стоп`.")
    else:
        if last_action == "combined_contact_add_noop_after_session":
            lines.append("Что дальше: очередь контактов закончилась; можно выбрать новый файл и начать новый цикл.")
        else:
            lines.append("Что дальше: можно снова нажать `Старт совместного режима`, чтобы продолжить общий цикл.")
    if invite_snapshot and str(invite_snapshot.get("status") or "") == "ready":
        lines.append(
            f"Контакты: осталось {invite_snapshot.get('pending_total') or 0}, добавлено {invite_snapshot.get('added_total') or 0}, ошибок {invite_snapshot.get('failed_total') or 0}"
        )
    if session_snapshot and str(session_snapshot.get("status") or "") != "missing":
        last_run = session_snapshot.get("last_run") if isinstance(session_snapshot.get("last_run"), dict) else {}
        if last_run:
            lines.append(
                f"Сессии: последнее отправлено {last_run.get('sent_count') or 0}, визитов {last_run.get('visit_count') or 0}, статус {last_run.get('status') or '-'}"
            )
            _append_message_items(
                lines,
                "Последние реально отправленные",
                list(last_run.get("sent_messages") or []) if isinstance(last_run.get("sent_messages"), list) else [],
            )
    lines.extend(["", format_session_targets_summary(session_targets)])
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
        f"Уже были в контактах: {payload.get('already_present_count') or 0}",
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
            self.combined_input_path_var = tk.StringVar()
            self.combined_job_dir_var = tk.StringVar()
            self.combined_preview_var = tk.StringVar(value="Список ещё не выбран")
            self.combined_step_pattern_var = tk.StringVar(value="12")

            self.session_config_path_var = tk.StringVar(value=str(DEFAULT_SESSION_CONFIG))
            self.session_new_target_var = tk.StringVar()
            self.session_new_target_label_var = tk.StringVar()
            self.session_new_target_kind_var = tk.StringVar(value="Контакт")
            self.session_auto_send_var = tk.BooleanVar(value=False)
            self.session_continuous_var = tk.BooleanVar(value=False)
            self.session_messages_per_cycle_var = tk.StringVar(value="1")
            self.session_total_limit_var = tk.StringVar(value="0")
            self.session_visit_count_var = tk.StringVar(value="6")
            self.session_view_min_var = tk.StringVar(value="3")
            self.session_view_max_var = tk.StringVar(value="6")
            self.session_timer_var = tk.StringVar(value="00:00:00")
            self.invite_status_var = tk.StringVar(value="Готово")
            self.session_status_var = tk.StringVar(value="Готово")
            self.combined_status_var = tk.StringVar(value="Готово")
            self.combined_phase_var = tk.StringVar(value=combined_phase_label("contact_add"))

            self._profiles: list[dict[str, Any]] = []
            self._session_targets: list[dict[str, Any]] = []
            self._active_tool_id = "telegram_invite_manager"
            self._active_processes: dict[str, subprocess.Popen[str]] = {}
            self._active_process_profiles: dict[str, str] = {}
            self._busy_controls: dict[str, list[Any]] = {
                "telegram_invite_manager": [],
                "telegram_session_runner": [],
                "telegram_combined_flow": [],
            }
            self._stop_controls: dict[str, list[Any]] = {
                "telegram_invite_manager": [],
                "telegram_session_runner": [],
                "telegram_combined_flow": [],
            }
            self._process_lock = threading.Lock()
            self._ui_queue: queue.Queue[tuple[str, str, dict[str, Any] | None, str, bool, Callable[[dict[str, Any]], None]]] = queue.Queue()
            self._ui_queue_after_id: str | None = None
            self._scroll_canvas: tk.Canvas | None = None
            self._session_timer_started_at: float | None = None
            self._session_timer_after_id: str | None = None
            self._monitor_after_ids: dict[str, str | None] = {
                "telegram_invite_manager": None,
                "telegram_session_runner": None,
                "telegram_combined_flow": None,
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
            self.combined_output: tk.Text | None = None
            self.combined_state_text: tk.Text | None = None
            self.combined_contact_text: tk.Text | None = None
            self.combined_session_text: tk.Text | None = None
            self.combined_targets_text: tk.Text | None = None
            self.session_targets_list: tk.Listbox | None = None
            self.session_templates_text: tk.Text | None = None
            self.combined_templates_text: tk.Text | None = None
            self._session_template_widgets: list[tk.Text] = []
            self._tool_buttons: dict[str, tk.Button] = {}
            self._tool_frames: dict[str, ttk.Frame] = {}

            self.invite_input_path_var.trace_add("write", self._sync_contact_job_dir)
            self.combined_input_path_var.trace_add("write", self._sync_combined_job_dir)

            self._build_ui()
            self._reload_profiles(initial=True)
            self._load_session_targets(show_feedback=False)
            self._switch_tool("telegram_invite_manager")
            self._ui_queue_after_id = self.after(120, self._drain_ui_queue)

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
            content = "\n".join(str(item) for item in templates)
            for widget in self._session_template_widgets:
                widget.delete("1.0", tk.END)
                if content:
                    widget.insert("1.0", content)

        def _session_templates(self) -> list[str]:
            if not self._session_template_widgets:
                return []
            focused = self.focus_get()
            source: tk.Text | None = None
            if isinstance(focused, tk.Text) and focused in self._session_template_widgets:
                source = focused
            elif self.session_templates_text is not None:
                source = self.session_templates_text
            else:
                source = self._session_template_widgets[0]
            content = source.get("1.0", tk.END)
            for widget in self._session_template_widgets:
                if widget is source:
                    continue
                current = widget.get("1.0", tk.END)
                if current != content:
                    widget.delete("1.0", tk.END)
                    widget.insert("1.0", content)
            return [
                line.strip()
                for line in content.splitlines()
                if line.strip()
            ]

        def _register_session_template_widget(self, widget: tk.Text, *, primary: bool = False) -> None:
            self._session_template_widgets.append(widget)
            widget.bind("<FocusOut>", lambda _event: self._session_templates(), add="+")
            if primary or self.session_templates_text is None:
                self.session_templates_text = widget

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
            if tool_id == "telegram_invite_manager":
                return self.invite_status_var
            if tool_id == "telegram_combined_flow":
                return self.combined_status_var
            return self.session_status_var

        def _output_widget_for_tool(self, tool_id: str) -> tk.Text | None:
            if tool_id == "telegram_invite_manager":
                return self.invite_output
            if tool_id == "telegram_combined_flow":
                return self.combined_output
            return self.session_output

        def _tool_label(self, tool_id: str) -> str:
            return {
                "telegram_invite_manager": "Добавить контакты из TXT",
                "telegram_session_runner": "Сессия и сообщения",
                "telegram_combined_flow": "Совместный режим",
            }.get(tool_id, tool_id)

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
                elif tool_id == "telegram_combined_flow":
                    self._refresh_combined_dashboard()
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
            profile_dir: str = "",
        ) -> None:
            with self._process_lock:
                existing = self._active_processes.get(tool_id)
                if existing is not None and existing.poll() is None:
                    messagebox.showinfo("Панель Telegram", "Сначала дождись завершения текущего действия или нажми `Стоп`.")
                    return
                conflict = active_profile_conflict(
                    self._active_process_profiles,
                    profile_dir,
                    current_tool_id=tool_id,
                )
                if conflict is not None:
                    conflicting_tool_id, _ = conflict
                    messagebox.showinfo(
                        "Панель Telegram",
                        (
                            "Этот Telegram-профиль уже занят другим живым действием.\n\n"
                            f"Активный режим: {self._tool_label(conflicting_tool_id)}\n"
                            "Сначала дождись завершения или нажми `Стоп` в активном режиме."
                        ),
                    )
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
                        if str(profile_dir).strip():
                            self._active_process_profiles[tool_id] = str(Path(profile_dir).expanduser().resolve())
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
                        self._active_process_profiles.pop(tool_id, None)
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
            self._ui_queue_after_id = None
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
                self._ui_queue_after_id = self.after(120, self._drain_ui_queue)

        def destroy(self) -> None:
            self._cancel_tool_monitor("telegram_invite_manager")
            self._cancel_tool_monitor("telegram_session_runner")
            self._cancel_tool_monitor("telegram_combined_flow")
            self._stop_session_timer()
            if self._ui_queue_after_id:
                try:
                    self.after_cancel(self._ui_queue_after_id)
                except tk.TclError:
                    pass
                self._ui_queue_after_id = None
            if self.profile_manager_window is not None and self.profile_manager_window.winfo_exists():
                try:
                    self.profile_manager_window.destroy()
                except tk.TclError:
                    pass
                self.profile_manager_window = None
            super().destroy()

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
                elif tool_id == "telegram_combined_flow":
                    try:
                        self._set_combined_phase(
                            "stopped",
                            last_action=action_label,
                            last_status="stopped",
                        )
                    except Exception:
                        pass
                    self._refresh_combined_dashboard()
                elif tool_id == "telegram_session_runner":
                    self._refresh_session_dashboard()
                return
            if error_text:
                self._status_var_for_tool(tool_id).set("Ошибка")
                self._log_event(tool_id, f"Ошибка: {action_label}")
                self._log_event(tool_id, error_text)
                if tool_id == "telegram_invite_manager":
                    self._refresh_invite_dashboard()
                elif tool_id == "telegram_combined_flow":
                    try:
                        self._save_combined_state(
                            last_action=action_label,
                            last_status="error",
                            last_summary=error_text,
                        )
                    except Exception:
                        pass
                    self._refresh_combined_dashboard()
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
            self._build_profile_status_section(content)
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

        def _build_profile_status_section(self, parent: ttk.Frame) -> None:
            body = self._create_card(
                parent,
                "3. Состояние профиля",
                "Этот блок вспомогательный: здесь детали выбранного профиля и сводка по всем найденным Telegram-пользователям.",
            )
            body.columnconfigure(0, weight=1)

            ttk.Label(body, text="Детали профиля", style="Field.TLabel").grid(
                row=0, column=0, sticky="w"
            )
            self.profile_details = self._create_readonly_text(body, height=5)
            self.profile_details.grid(row=1, column=0, sticky="nsew", pady=(6, 0))
            ttk.Label(body, text="Все найденные профили", style="Field.TLabel").grid(
                row=2, column=0, sticky="w", pady=(14, 0)
            )
            self.profile_overview = self._create_readonly_text(body, height=4)
            self.profile_overview.grid(row=3, column=0, sticky="nsew", pady=(6, 0))

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
                ("telegram_session_runner", "Сессия и сообщения"),
                ("telegram_combined_flow", "Совместный режим: Добавить → Сессия"),
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
                text="`Добавить контакты из TXT` запускает реальное добавление контактов. `Старт сессии` управляет random walk и сообщениями. `Совместный режим` ведёт по сценарию `Добавить → Сессия` на одном профиле.",
                style="CardSubtitle.TLabel",
            ).pack(anchor="w", pady=(10, 0))

        def _build_tool_content(self, parent: ttk.Frame) -> None:
            container = ttk.Frame(parent, style="App.TFrame")
            container.pack(fill=tk.BOTH, expand=True)

            invite_frame = ttk.Frame(container, style="App.TFrame")
            session_frame = ttk.Frame(container, style="App.TFrame")
            combined_frame = ttk.Frame(container, style="App.TFrame")
            invite_frame.grid(row=0, column=0, sticky="nsew")
            session_frame.grid(row=0, column=0, sticky="nsew")
            combined_frame.grid(row=0, column=0, sticky="nsew")
            container.columnconfigure(0, weight=1)
            container.rowconfigure(0, weight=1)

            self._tool_frames["telegram_invite_manager"] = invite_frame
            self._tool_frames["telegram_session_runner"] = session_frame
            self._tool_frames["telegram_combined_flow"] = combined_frame

            self._build_invite_view(invite_frame)
            self._build_session_view(session_frame)
            self._build_combined_view(combined_frame)

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
                "Этот экран отдельно управляет живой Telegram-сессией: сверху сразу видны настройки визитов и отправки, ниже — адресаты, текст, история и живой лог.",
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

            settings_panel = self._create_inline_panel(
                body,
                "Шаг 2. Настройки сессии",
                "Эти параметры теперь наверху: сколько ходить по чатам, сколько времени держать чат открытым и сколько сообщений отправлять.",
            )
            settings_panel.grid(row=3, column=0, columnspan=2, sticky="nsew", pady=(6, 0))
            settings_panel.columnconfigure(1, weight=1)
            settings_panel.columnconfigure(3, weight=1)

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
                row=2, column=2, sticky="w", padx=(16, 0)
            )
            ttk.Entry(settings_panel, textvariable=self.session_view_min_var, width=10).grid(
                row=2, column=3, sticky="w", padx=(12, 0)
            )
            ttk.Label(
                settings_panel,
                text="Минимальная случайная пауза, сколько пользователь находится в открытом чате.",
                style="CardSubtitle.TLabel",
            ).grid(row=3, column=2, columnspan=2, sticky="w", padx=(16, 0), pady=(4, 10))

            ttk.Label(settings_panel, text="Максимум секунд в чате", style="Field.TLabel").grid(
                row=4, column=0, sticky="w"
            )
            ttk.Entry(settings_panel, textvariable=self.session_view_max_var, width=10).grid(
                row=4, column=1, sticky="w", padx=(12, 0)
            )
            ttk.Label(
                settings_panel,
                text="Максимальная случайная пауза в одном чате.",
                style="CardSubtitle.TLabel",
            ).grid(row=5, column=0, columnspan=2, sticky="w", pady=(4, 10))

            ttk.Label(settings_panel, text="Сообщений за один цикл", style="Field.TLabel").grid(
                row=4, column=2, sticky="w", padx=(16, 0)
            )
            ttk.Entry(settings_panel, textvariable=self.session_messages_per_cycle_var, width=10).grid(
                row=4, column=3, sticky="w", padx=(12, 0)
            )
            ttk.Label(
                settings_panel,
                text="Сколько сообщений пытаться отправить за один проход по сессии.",
                style="CardSubtitle.TLabel",
            ).grid(row=5, column=2, columnspan=2, sticky="w", padx=(16, 0), pady=(4, 10))

            ttk.Label(settings_panel, text="Максимум отправить за всю сессию", style="Field.TLabel").grid(
                row=6, column=0, sticky="w"
            )
            ttk.Entry(settings_panel, textvariable=self.session_total_limit_var, width=10).grid(
                row=6, column=1, sticky="w", padx=(12, 0)
            )
            ttk.Label(
                settings_panel,
                text="Поставь `0`, если лимит не нужен и сессия должна слать сообщения до ручного `Стоп`.",
                style="CardSubtitle.TLabel",
            ).grid(row=7, column=0, columnspan=2, sticky="w", pady=(4, 10))

            ttk.Checkbutton(
                settings_panel,
                text="Отправлять сообщения сразу, а не оставлять в строке ввода",
                variable=self.session_auto_send_var,
            ).grid(row=6, column=2, columnspan=2, sticky="w", padx=(16, 0))
            ttk.Checkbutton(
                settings_panel,
                text="Крутить сессию непрерывно до нажатия `Стоп`",
                variable=self.session_continuous_var,
            ).grid(row=7, column=2, columnspan=2, sticky="w", padx=(16, 0), pady=(8, 0))

            ttk.Label(
                body,
                text="Текущий профиль сверху будет автоматически подставлен в runtime-config перед запуском.",
                style="CardSubtitle.TLabel",
            ).grid(row=4, column=0, columnspan=2, sticky="w", pady=(12, 0))

            editors_row = ttk.Frame(body, style="Card.TFrame")
            editors_row.grid(row=5, column=0, columnspan=2, sticky="nsew", pady=(12, 0))
            editors_row.columnconfigure(0, weight=1)
            editors_row.columnconfigure(1, weight=1)

            recipients_panel = self._create_inline_panel(
                editors_row,
                "Шаг 3. Кому писать",
                "Список адресатов и ручное добавление. Это отдельный блок, чтобы он не спорил по месту с настройками сессии.",
            )
            recipients_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
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

            templates_panel = self._create_inline_panel(
                editors_row,
                "Шаг 4. Текст сообщения",
                "Одна строка = один шаблон. Этот блок справа, чтобы одновременно видеть и список адресатов, и тексты.",
            )
            templates_panel.grid(row=0, column=1, sticky="nsew")
            templates_panel.columnconfigure(0, weight=1)
            session_templates = tk.Text(
                templates_panel,
                wrap="word",
                height=12,
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
            session_templates.grid(row=2, column=0, sticky="nsew")
            self._bind_scroll_to_widget(session_templates)
            self._register_session_template_widget(session_templates, primary=True)

            summary_panel = self._create_inline_panel(
                body,
                "Сводка и подтверждение отправки",
                "Здесь видно общий прогресс, последний запуск и сообщения, которые не были отправлены.",
            )
            summary_panel.grid(row=6, column=0, sticky="nsew", pady=(14, 0), padx=(0, 10))
            summary_panel.columnconfigure(0, weight=1)
            self.session_summary_text = self._create_readonly_text(summary_panel, height=10)
            self.session_summary_text.grid(row=2, column=0, sticky="nsew")
            self._bind_scroll_to_widget(self.session_summary_text)

            history_panel = self._create_inline_panel(
                body,
                "История запусков сессии",
                "Показывает последние run.json: статус, визиты, сколько сообщений действительно отправлено.",
            )
            history_panel.grid(row=6, column=1, sticky="nsew", pady=(14, 0))
            history_panel.columnconfigure(0, weight=1)
            self.session_history_text = self._create_readonly_text(history_panel, height=10)
            self.session_history_text.grid(row=2, column=0, sticky="nsew")
            self._bind_scroll_to_widget(self.session_history_text)

            ttk.Label(body, text="Живой статус и лог", style="Field.TLabel").grid(
                row=7, column=0, sticky="w", pady=(16, 0)
            )
            self.session_output = self._create_readonly_text(body, height=16)
            self.session_output.grid(row=8, column=0, columnspan=2, sticky="nsew", pady=(6, 0))
            self._bind_scroll_to_widget(self.session_output)
            body.rowconfigure(8, weight=1)

        def _build_combined_view(self, parent: ttk.Frame) -> None:
            body = self._create_card(
                parent,
                "Инструмент: Совместный режим `Добавить → Сессия`",
                "Этот экран ведёт один профиль по цепочке: сначала добавляем контакты из файла, затем на том же профиле запускаем сессию и сообщения. Одновременно два живых действия на одном окне Telegram здесь не допускаются.",
                expand=True,
            )
            body.columnconfigure(0, weight=1)
            body.columnconfigure(1, weight=1)

            top_buttons = ttk.Frame(body, style="Card.TFrame")
            top_buttons.grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 12))
            combined_start_button = ttk.Button(
                top_buttons,
                text="Старт совместного режима",
                style="Accent.TButton",
                command=self._combined_start_flow,
            )
            combined_start_button.pack(side=tk.LEFT)
            self._register_busy_widget("telegram_combined_flow", combined_start_button)
            combined_refresh_button = ttk.Button(
                top_buttons,
                text="Обновить экран",
                command=self._refresh_combined_dashboard,
            )
            combined_refresh_button.pack(side=tk.LEFT, padx=(10, 0))
            self._register_busy_widget("telegram_combined_flow", combined_refresh_button)
            combined_stop_button = ttk.Button(
                top_buttons,
                text="Стоп",
                command=lambda: self._stop_tool_process("telegram_combined_flow"),
                state="disabled",
            )
            combined_stop_button.pack(side=tk.LEFT, padx=(10, 0))
            self._register_stop_widget("telegram_combined_flow", combined_stop_button)
            ttk.Label(
                top_buttons,
                textvariable=self.combined_status_var,
                style="CardSubtitle.TLabel",
            ).pack(side=tk.LEFT, padx=(16, 0))
            ttk.Label(
                top_buttons,
                textvariable=self.combined_phase_var,
                style="CardSubtitle.TLabel",
            ).pack(side=tk.LEFT, padx=(12, 0))

            ttk.Label(body, text="Шаг 1. Файл контактов", style="Field.TLabel").grid(
                row=1, column=0, sticky="w"
            )
            file_row = ttk.Frame(body, style="Card.TFrame")
            file_row.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(4, 10))
            file_row.columnconfigure(0, weight=1)
            ttk.Entry(file_row, textvariable=self.combined_input_path_var).grid(row=0, column=0, sticky="ew")
            combined_choose_file_button = ttk.Button(
                file_row,
                text="Загрузить TXT / CSV / JSON",
                command=self._choose_combined_input,
            )
            combined_choose_file_button.grid(row=0, column=1, padx=(10, 0))
            self._register_busy_widget("telegram_combined_flow", combined_choose_file_button)
            ttk.Label(body, textvariable=self.combined_preview_var, style="CardSubtitle.TLabel").grid(
                row=3, column=0, columnspan=2, sticky="w"
            )
            ttk.Label(
                body,
                text="Один `Старт` сам крутит общий цикл. Шаги берутся из шаблона ниже: `1` = добавление, `2` = сессия.",
                style="CardSubtitle.TLabel",
            ).grid(row=4, column=0, columnspan=2, sticky="w", pady=(2, 0))

            ttk.Label(body, text="Шаг 2. Папка задачи добавления", style="Field.TLabel").grid(
                row=5, column=0, sticky="w", pady=(8, 0)
            )
            ttk.Entry(body, textvariable=self.combined_job_dir_var).grid(
                row=6, column=0, columnspan=2, sticky="ew", pady=(4, 10)
            )

            limit_row = ttk.Frame(body, style="Card.TFrame")
            limit_row.grid(row=7, column=0, columnspan=2, sticky="w")
            ttk.Label(limit_row, text="Сколько username обработать за один запуск", style="Field.TLabel").pack(
                side=tk.LEFT
            )
            ttk.Entry(limit_row, textvariable=self.invite_limit_var, width=8).pack(
                side=tk.LEFT,
                padx=(10, 0),
            )
            ttk.Label(limit_row, text="Шаблон шагов", style="Field.TLabel").pack(side=tk.LEFT, padx=(20, 0))
            ttk.Entry(limit_row, textvariable=self.combined_step_pattern_var, width=22).pack(
                side=tk.LEFT,
                padx=(10, 0),
            )
            ttk.Label(
                limit_row,
                text="Например: 11,2,1111,22,1,222,1111",
                style="CardSubtitle.TLabel",
            ).pack(side=tk.LEFT, padx=(10, 0))

            ttk.Label(body, text="Шаг 3. Что уже произошло", style="Field.TLabel").grid(
                row=8, column=0, sticky="w", pady=(10, 0)
            )
            self.combined_state_text = self._create_readonly_text(body, height=9)
            self.combined_state_text.grid(row=9, column=0, columnspan=2, sticky="nsew", pady=(6, 0))
            self._bind_scroll_to_widget(self.combined_state_text)

            ttk.Label(body, text="Шаг 4. Настройки сессии и сообщений", style="Field.TLabel").grid(
                row=10, column=0, sticky="w", pady=(14, 0)
            )
            settings_row = ttk.Frame(body, style="Card.TFrame")
            settings_row.grid(row=11, column=0, columnspan=2, sticky="nsew", pady=(6, 0))
            settings_row.columnconfigure(0, weight=1)
            settings_row.columnconfigure(1, weight=1)

            combined_settings_panel = self._create_inline_panel(
                settings_row,
                "Настройки сессии",
                "Здесь всегда видны визиты за цикл, время в чате, число сообщений, лимит, автоотправка и режим до `Стоп`.",
            )
            combined_settings_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
            combined_settings_panel.columnconfigure(1, weight=1)
            combined_settings_panel.columnconfigure(3, weight=1)

            ttk.Label(combined_settings_panel, text="Конфиг режима", style="Field.TLabel").grid(
                row=2, column=0, sticky="w"
            )
            combined_config_row = ttk.Frame(combined_settings_panel, style="Card.TFrame")
            combined_config_row.grid(row=3, column=0, columnspan=4, sticky="ew", pady=(4, 10))
            combined_config_row.columnconfigure(0, weight=1)
            ttk.Entry(combined_config_row, textvariable=self.session_config_path_var).grid(
                row=0, column=0, sticky="ew"
            )
            combined_choose_config_button = ttk.Button(
                combined_config_row,
                text="Выбрать конфиг",
                command=self._choose_session_config,
            )
            combined_choose_config_button.grid(row=0, column=1, padx=(10, 0))
            self._register_busy_widget("telegram_combined_flow", combined_choose_config_button)
            combined_load_targets_button = ttk.Button(
                combined_config_row,
                text="Загрузить адресатов",
                command=self._load_session_targets,
            )
            combined_load_targets_button.grid(row=0, column=2, padx=(10, 0))
            self._register_busy_widget("telegram_combined_flow", combined_load_targets_button)

            ttk.Label(combined_settings_panel, text="Визитов за цикл", style="Field.TLabel").grid(
                row=4, column=0, sticky="w"
            )
            ttk.Entry(combined_settings_panel, textvariable=self.session_visit_count_var, width=10).grid(
                row=4, column=1, sticky="w", padx=(12, 0)
            )
            ttk.Label(combined_settings_panel, text="Мин. секунд в чате", style="Field.TLabel").grid(
                row=4, column=2, sticky="w", padx=(16, 0)
            )
            ttk.Entry(combined_settings_panel, textvariable=self.session_view_min_var, width=10).grid(
                row=4, column=3, sticky="w", padx=(12, 0)
            )
            ttk.Label(combined_settings_panel, text="Макс. секунд в чате", style="Field.TLabel").grid(
                row=5, column=0, sticky="w", pady=(8, 0)
            )
            ttk.Entry(combined_settings_panel, textvariable=self.session_view_max_var, width=10).grid(
                row=5, column=1, sticky="w", padx=(12, 0), pady=(8, 0)
            )
            ttk.Label(combined_settings_panel, text="Сообщений за цикл", style="Field.TLabel").grid(
                row=5, column=2, sticky="w", padx=(16, 0), pady=(8, 0)
            )
            ttk.Entry(combined_settings_panel, textvariable=self.session_messages_per_cycle_var, width=10).grid(
                row=5, column=3, sticky="w", padx=(12, 0), pady=(8, 0)
            )
            ttk.Label(combined_settings_panel, text="Общий лимит сообщений", style="Field.TLabel").grid(
                row=6, column=0, sticky="w", pady=(8, 0)
            )
            ttk.Entry(combined_settings_panel, textvariable=self.session_total_limit_var, width=10).grid(
                row=6, column=1, sticky="w", padx=(12, 0), pady=(8, 0)
            )
            ttk.Checkbutton(
                combined_settings_panel,
                text="Автоотправка",
                variable=self.session_auto_send_var,
            ).grid(row=6, column=2, columnspan=2, sticky="w", padx=(16, 0), pady=(8, 0))
            ttk.Checkbutton(
                combined_settings_panel,
                text="Непрерывно до `Стоп`",
                variable=self.session_continuous_var,
            ).grid(row=7, column=2, columnspan=2, sticky="w", padx=(16, 0), pady=(8, 0))

            combined_targets_panel = self._create_inline_panel(
                settings_row,
                "Кому писать",
                "Совместный режим не берёт адресатов автоматически из TXT. Он использует текущий список адресатов режима сессии.",
            )
            combined_targets_panel.grid(row=0, column=1, sticky="nsew")
            combined_targets_panel.columnconfigure(0, weight=1)
            self.combined_targets_text = self._create_readonly_text(combined_targets_panel, height=10)
            self.combined_targets_text.grid(row=2, column=0, sticky="nsew")
            self._bind_scroll_to_widget(self.combined_targets_text)
            open_session_editor_button = ttk.Button(
                combined_targets_panel,
                text="Открыть экран сессии для редактирования адресатов",
                command=self._combined_switch_to_session,
            )
            open_session_editor_button.grid(row=3, column=0, sticky="ew", pady=(10, 0))
            self._register_busy_widget("telegram_combined_flow", open_session_editor_button)

            templates_panel = self._create_inline_panel(
                body,
                "Тексты сообщений",
                "Одна строка = один шаблон. Это тот же текстовый пул, который использует отдельный режим `Сессия и сообщения`.",
            )
            templates_panel.grid(row=12, column=0, sticky="nsew", pady=(14, 0), padx=(0, 10))
            templates_panel.columnconfigure(0, weight=1)
            combined_templates = tk.Text(
                templates_panel,
                wrap="word",
                height=8,
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
            combined_templates.grid(row=2, column=0, sticky="nsew")
            self._bind_scroll_to_widget(combined_templates)
            self.combined_templates_text = combined_templates
            self._register_session_template_widget(combined_templates)

            combined_session_panel = self._create_inline_panel(
                body,
                "Сводка по контактам и сессиям",
                "Слева — состояние шага добавления, справа — последний результат session runner.",
            )
            combined_session_panel.grid(row=12, column=1, sticky="nsew", pady=(14, 0))
            combined_session_panel.columnconfigure(0, weight=1)
            combined_session_panel.rowconfigure(2, weight=1)
            combined_split = ttk.Frame(combined_session_panel, style="Card.TFrame")
            combined_split.grid(row=2, column=0, sticky="nsew")
            combined_split.columnconfigure(0, weight=1)
            combined_split.columnconfigure(1, weight=1)
            self.combined_contact_text = self._create_readonly_text(combined_split, height=8)
            self.combined_contact_text.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
            self._bind_scroll_to_widget(self.combined_contact_text)
            self.combined_session_text = self._create_readonly_text(combined_split, height=8)
            self.combined_session_text.grid(row=0, column=1, sticky="nsew")
            self._bind_scroll_to_widget(self.combined_session_text)

            ttk.Label(body, text="Общий лог совместного режима", style="Field.TLabel").grid(
                row=13, column=0, sticky="w", pady=(16, 0)
            )
            self.combined_output = self._create_readonly_text(body, height=16)
            self.combined_output.grid(row=14, column=0, columnspan=2, sticky="nsew", pady=(6, 0))
            self._bind_scroll_to_widget(self.combined_output)
            body.rowconfigure(14, weight=1)

        def _refresh_summary(self) -> None:
            selected_profile = self._selected_profile()
            profile_part = (
                format_profile_label(selected_profile) if selected_profile is not None else "профиль не выбран"
            )
            active_label = (
                "Добавление контактов из TXT"
                if self._active_tool_id == "telegram_invite_manager"
                else (
                    "Сессия и сообщения"
                    if self._active_tool_id == "telegram_session_runner"
                    else "Совместный режим"
                )
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
                if self.combined_input_path_var.get().strip() and not self.combined_job_dir_var.get().strip():
                    self._sync_combined_job_dir()
                if self._active_tool_id == "telegram_combined_flow":
                    self._refresh_combined_dashboard()
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
            elif tool_id == "telegram_combined_flow":
                self._set_readonly_text(
                    self.combined_output,
                    "\n".join(
                        [
                            "Совместный режим `Добавить → Сессия`",
                            "1. Сверху выбери Telegram-профиль.",
                            "2. Загрузи файл контактов и нажми `1. Старт добавления`.",
                            "3. После шага добавления перейди к сессии и нажми `2. Старт сессии`.",
                        ]
                    ),
                )
                self._refresh_combined_dashboard()
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

        def _choose_combined_input(self) -> None:
            if filedialog is None:  # pragma: no cover - depends on tkinter extras
                return
            selected = filedialog.askopenfilename(
                title="Выбери файл контактов для совместного режима",
                filetypes=[
                    ("Поддерживаемые файлы", "*.txt *.csv *.json"),
                    ("Текстовые файлы", "*.txt"),
                    ("CSV", "*.csv"),
                    ("JSON", "*.json"),
                    ("Все файлы", "*"),
                ],
            )
            if selected:
                self.combined_input_path_var.set(selected)
                self.combined_job_dir_var.set("")
                self._sync_combined_job_dir()
                self.combined_status_var.set("Файл выбран")
                self._log_event("telegram_combined_flow", f"Выбран файл контактов: {selected}")
                self._set_combined_phase(
                    "contact_add",
                    input_path=selected,
                    invite_job_dir=self.combined_job_dir_var.get().strip(),
                    last_action="chosen_contact_file",
                    last_status="ready",
                )
                self._refresh_combined_dashboard()

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
                if self._active_tool_id == "telegram_combined_flow":
                    try:
                        self._save_combined_state(session_config_path=selected)
                    except Exception:
                        pass
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
            preview_context = self._session_preview_context()
            self._set_readonly_text(
                self.session_summary_text,
                format_session_operator_summary(snapshot, **preview_context),
            )
            self._set_readonly_text(self.session_history_text, format_session_history(snapshot))

        def _sync_combined_job_dir(self, *_args: object) -> None:
            input_path = self.combined_input_path_var.get().strip()
            if not input_path or self.combined_job_dir_var.get().strip():
                return
            profile = self._selected_profile()
            profile_name = str((profile or {}).get("profile_name") or "profile").strip() or "profile"
            self.combined_job_dir_var.set(
                str(
                    default_contact_add_job_dir(
                        profile_name=profile_name,
                        input_path=input_path,
                        output_root=DEFAULT_INVITE_OUTPUT_ROOT,
                    )
                )
            )

        def _selected_profile_identity(self) -> tuple[str, str]:
            profile = self._selected_profile()
            if profile is None:
                raise ValueError("Сначала выбери Telegram-профиль сверху.")
            return (
                str(profile.get("profile_name") or "").strip() or "profile",
                str(profile.get("profile_dir") or "").strip(),
            )

        def _load_combined_state(self) -> dict[str, Any]:
            profile_name, profile_dir = self._selected_profile_identity()
            return load_combined_flow_state(
                profile_name=profile_name,
                profile_dir=profile_dir,
                state_root=DEFAULT_PANEL_STATE_ROOT,
            )

        def _save_combined_state(self, **updates: Any) -> dict[str, Any]:
            profile_name, profile_dir = self._selected_profile_identity()
            current = load_combined_flow_state(
                profile_name=profile_name,
                profile_dir=profile_dir,
                state_root=DEFAULT_PANEL_STATE_ROOT,
            )
            current.update(updates)
            save_combined_flow_state(
                profile_name=profile_name,
                profile_dir=profile_dir,
                payload=current,
                state_root=DEFAULT_PANEL_STATE_ROOT,
            )
            return current

        def _set_combined_phase(self, phase: str, **extra: Any) -> dict[str, Any]:
            state = self._save_combined_state(phase=phase, **extra)
            self.combined_phase_var.set(combined_phase_label(phase))
            return state

        def _session_preview_context(self) -> dict[str, Any]:
            return {
                "session_targets": list(self._session_targets),
                "session_templates": self._session_templates(),
                "visits_per_cycle": _safe_preview_int(self.session_visit_count_var.get()),
                "view_min_seconds": _safe_preview_int(self.session_view_min_var.get()),
                "view_max_seconds": _safe_preview_int(self.session_view_max_var.get()),
                "messages_per_cycle": _safe_preview_int(self.session_messages_per_cycle_var.get()),
                "total_message_limit": _safe_preview_int(self.session_total_limit_var.get()),
                "auto_send": bool(self.session_auto_send_var.get()),
                "continuous": bool(self.session_continuous_var.get()),
            }

        def _combined_pattern_tokens(self) -> list[str]:
            tokens = parse_combined_step_pattern(self.combined_step_pattern_var.get())
            if not tokens:
                raise ValueError("Шаблон совместного режима должен содержать хотя бы один шаг: `1` или `2`.")
            return tokens

        def _combined_pattern_text(self) -> str:
            return self.combined_step_pattern_var.get().strip()

        def _combined_current_step(self, state: dict[str, Any] | None = None) -> tuple[list[str], int, str]:
            current_state = state or self._load_combined_state()
            raw_pattern = str(current_state.get("step_pattern") or "").strip()
            ui_pattern = self._combined_pattern_text()
            if raw_pattern != ui_pattern:
                tokens = self._combined_pattern_tokens()
                cursor = 0
            else:
                tokens = parse_combined_step_pattern(raw_pattern) or self._combined_pattern_tokens()
                cursor = max(0, _safe_preview_int(current_state.get("step_cursor")))
            step_code = tokens[cursor % len(tokens)]
            return tokens, cursor, step_code

        def _combined_advance_cursor(self, state: dict[str, Any]) -> tuple[list[str], int, str]:
            tokens, cursor, _step_code = self._combined_current_step(state)
            next_cursor = (cursor + 1) % len(tokens)
            next_step = tokens[next_cursor]
            return tokens, next_cursor, next_step

        def _combined_autostart_next_step(self, step_code: str) -> None:
            if str(step_code) == "1":
                self._combined_start_contact_add()
            else:
                self._combined_start_session(force=True)

        def _combined_start_flow(self) -> None:
            try:
                state = self._load_combined_state()
                tokens, cursor, step_code = self._combined_current_step(state)
            except Exception as exc:
                messagebox.showerror("Панель Telegram", f"Не удалось подготовить совместный режим:\n{exc}")
                return
            self._save_combined_state(
                step_pattern=self._combined_pattern_text(),
                step_cursor=cursor,
                step_label=combined_step_label(step_code),
            )
            self.combined_status_var.set(f"Следующий шаг по шаблону: {combined_step_label(step_code)}")
            self._log_event(
                "telegram_combined_flow",
                f"Старт общего режима: шаг {cursor + 1}/{len(tokens)} по шаблону -> {combined_step_label(step_code)}",
            )
            self._combined_autostart_next_step(step_code)

        def _combined_targets_summary(self) -> str:
            return format_session_targets_summary(self._session_targets)

        def _combined_switch_to_session(self) -> None:
            self._switch_tool("telegram_session_runner")

        def _combined_status_from_state(self, state: dict[str, Any]) -> str:
            phase = str(state.get("phase") or "contact_add").strip()
            last_status = str(state.get("last_status") or "").strip().lower()
            last_action = str(state.get("last_action") or "").strip()
            if phase == "contact_add":
                if last_action == "combined_session_finished_next_contact":
                    return "Есть ещё username, запускается следующий шаг добавления"
                return "Готов к шагу добавления"
            if phase == "review":
                return "Есть ошибки, проверь лог и перезапусти общий режим"
            if phase == "session_ready":
                if last_action == "combined_contact_add_noop":
                    return "Новых username для добавления нет; выбери другой файл или перезапусти общий режим"
                if last_action == "combined_contact_add_finished_auto":
                    return "Контакты готовы, сейчас запустится сессия"
                return "Контакты готовы, общий режим может продолжать следующий шаг"
            if phase == "session_running":
                return "Сессия выполняется"
            if phase == "stopped":
                if last_action == "combined_contact_add_noop_after_session":
                    return "Очередь контактов закончилась, совместный режим завершён"
                if last_action == "combined_session_finished":
                    if last_status == "completed":
                        return "Совместный режим завершил шаг сессии"
                    if last_status == "stopped":
                        return "Сессия остановлена"
                    if last_status:
                        return f"Сессия завершилась со статусом: {last_status}"
                if last_action == "combined_contact_add_finished":
                    if last_status == "completed":
                        return "Шаг добавления завершён"
                    if last_status == "completed_with_errors":
                        return "Шаг добавления завершён с ошибками"
                    if last_status:
                        return f"Шаг добавления завершился со статусом: {last_status}"
                if last_status:
                    return f"Последний статус: {last_status}"
            return "Готово"

        def _refresh_combined_dashboard(self) -> None:
            profile = self._selected_profile()
            if profile is None:
                self._set_readonly_text(
                    self.combined_state_text,
                    "Совместный режим\nСначала выбери Telegram-профиль сверху.",
                )
                self._set_readonly_text(self.combined_contact_text, "Контакты\nПрофиль не выбран.")
                self._set_readonly_text(self.combined_session_text, "Сессия\nПрофиль не выбран.")
                self._set_readonly_text(self.combined_targets_text, "Адресаты\nПрофиль не выбран.")
                return
            state = self._load_combined_state()
            self.combined_phase_var.set(combined_phase_label(str(state.get("phase") or "contact_add")))
            self.combined_status_var.set(self._combined_status_from_state(state))
            if state.get("input_path"):
                self.combined_input_path_var.set(str(state.get("input_path") or ""))
            if state.get("invite_job_dir"):
                self.combined_job_dir_var.set(str(state.get("invite_job_dir") or ""))
            if state.get("session_config_path"):
                self.session_config_path_var.set(str(state.get("session_config_path") or ""))
            if state.get("step_pattern"):
                self.combined_step_pattern_var.set(str(state.get("step_pattern") or ""))
            input_path = self.combined_input_path_var.get().strip()
            invite_snapshot: dict[str, Any] | None = None
            preview_text = "Список ещё не выбран"
            if self.combined_job_dir_var.get().strip():
                invite_snapshot = contact_job_snapshot(self.combined_job_dir_var.get().strip())
            if input_path:
                try:
                    preview = preview_invite_input_file(input_path)
                    preview_text = (
                        f"Уникальных username: {preview.get('unique_usernames') or 0} · "
                        f"дубликатов: {preview.get('duplicates') or 0} · "
                        f"ошибок: {preview.get('invalid_count') or 0}"
                    )
                except Exception as exc:
                    preview_text = f"Не удалось прочитать файл: {exc}"
            self.combined_preview_var.set(preview_text)
            session_snapshot = session_history_snapshot(
                state_file=DEFAULT_SESSION_STATE_FILE,
                runs_dir=DEFAULT_SESSION_RUNS_DIR,
            )
            preview_context = self._session_preview_context()
            profile_label = format_profile_label(profile)
            self._set_readonly_text(
                self.combined_state_text,
                format_combined_flow_state(
                    state,
                    profile_label=profile_label,
                    invite_snapshot=invite_snapshot,
                    session_snapshot=session_snapshot,
                    **preview_context,
                ),
            )
            if invite_snapshot is None:
                if input_path:
                    try:
                        preview = preview_invite_input_file(input_path)
                        self._set_readonly_text(self.combined_contact_text, format_invite_input_preview(preview))
                    except Exception as exc:
                        self._set_readonly_text(self.combined_contact_text, f"Не удалось прочитать список username:\n{exc}")
                else:
                    self._set_readonly_text(
                        self.combined_contact_text,
                        "Контакты\nВыбери файл контактов и нажми `1. Старт добавления`.",
                    )
            else:
                contact_text = format_contact_dashboard_snapshot(invite_snapshot)
                contact_text += "\n\n" + format_contact_errors(invite_snapshot)
                self._set_readonly_text(self.combined_contact_text, contact_text)
            self._set_readonly_text(self.combined_session_text, format_session_dashboard_snapshot(session_snapshot))
            self._set_readonly_text(self.combined_targets_text, self._combined_targets_summary())

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
                profile_dir=str(selected_profile.get("profile_dir") or ""),
            )

        def _combined_resolved_job_dir(self) -> Path:
            job_dir = self.combined_job_dir_var.get().strip()
            if job_dir:
                return Path(job_dir).expanduser().resolve()
            input_path = self.combined_input_path_var.get().strip()
            if not input_path:
                raise ValueError("Выбери файл контактов для совместного режима.")
            profile = self._selected_profile()
            profile_name = str((profile or {}).get("profile_name") or "profile").strip() or "profile"
            resolved = default_contact_add_job_dir(
                profile_name=profile_name,
                input_path=input_path,
                output_root=DEFAULT_INVITE_OUTPUT_ROOT,
            )
            self.combined_job_dir_var.set(str(resolved))
            return resolved

        def _combined_start_contact_add(self) -> None:
            input_path = self.combined_input_path_var.get().strip()
            if not input_path:
                messagebox.showinfo("Панель Telegram", "Сначала выбери файл контактов для совместного режима.")
                return
            selected_profile = self._selected_profile()
            if selected_profile is None:
                messagebox.showinfo("Панель Telegram", "Сначала выбери Telegram-профиль сверху.")
                return
            try:
                limit = max(int(self.invite_limit_var.get() or "0"), 0)
            except ValueError:
                limit = 0
            try:
                job_dir = self._combined_resolved_job_dir()
                command = contact_add_batch_command(
                    input_path=input_path,
                    job_dir=job_dir,
                    profile_name=str(selected_profile.get("profile_name") or ""),
                    portable_profile_dir=str(selected_profile.get("profile_dir") or ""),
                    account_username=str((selected_profile.get("account") or {}).get("username") or ""),
                    account_label=str((selected_profile.get("account") or {}).get("label") or ""),
                    limit=limit,
                    statuses=["new", "checked"],
                )
            except Exception as exc:
                messagebox.showerror("Панель Telegram", f"Не удалось подготовить совместный шаг добавления:\n{exc}")
                return
            try:
                tokens, cursor, step_code = self._combined_current_step()
            except Exception:
                tokens, cursor, step_code = (["1", "2"], 0, "1")
            self._set_combined_phase(
                "contact_add",
                input_path=input_path,
                invite_job_dir=str(job_dir),
                step_pattern=self._combined_pattern_text(),
                step_cursor=cursor,
                step_label=combined_step_label(step_code),
                last_action="combined_contact_add_started",
                last_status="running",
                session_config_path=self.session_config_path_var.get().strip(),
            )
            self._start_json_command(
                tool_id="telegram_combined_flow",
                action_label="совместный шаг: добавление контактов",
                command=command,
                on_success=self._on_combined_contact_add_success,
                monitor_active_state=True,
                profile_dir=str(selected_profile.get("profile_dir") or ""),
            )

        def _combined_start_session(self, force: bool = False) -> None:
            try:
                state = self._load_combined_state()
            except Exception as exc:
                messagebox.showerror("Панель Telegram", f"Не удалось прочитать состояние совместного режима:\n{exc}")
                return
            phase = str(state.get("phase") or "contact_add")
            if phase not in {"session_ready", "stopped"} and not force:
                messagebox.showinfo(
                    "Панель Telegram",
                    "Этот шаг сессии ещё не готов. Запусти общий режим кнопкой `Старт совместного режима`.",
                )
                return
            selected_profile = self._selected_profile()
            if selected_profile is None:
                messagebox.showinfo("Панель Telegram", "Сначала выбери Telegram-профиль сверху.")
                return
            try:
                runtime_config = self._build_session_runtime_config()
                command = session_run_command(
                    config_path=runtime_config,
                    auto_send=bool(self.session_auto_send_var.get()),
                    continuous=bool(self.session_continuous_var.get()),
                )
            except Exception as exc:
                messagebox.showerror("Панель Telegram", f"Не удалось подготовить совместный шаг сессии:\n{exc}")
                return
            try:
                tokens, cursor, step_code = self._combined_current_step(state)
            except Exception:
                tokens, cursor, step_code = (["1", "2"], 1, "2")
            self._set_combined_phase(
                "session_running",
                input_path=self.combined_input_path_var.get().strip(),
                invite_job_dir=self.combined_job_dir_var.get().strip(),
                session_config_path=self.session_config_path_var.get().strip(),
                step_pattern=self._combined_pattern_text(),
                step_cursor=cursor,
                step_label=combined_step_label(step_code),
                last_runtime_config_path=str(runtime_config),
                last_action="combined_session_started",
                last_status="running",
            )
            self._start_json_command(
                tool_id="telegram_combined_flow",
                action_label="совместный шаг: запуск сессии",
                command=command,
                on_success=lambda payload, runtime_config=runtime_config: self._on_combined_session_success(
                    payload,
                    runtime_config,
                ),
                monitor_active_state=True,
                profile_dir=str(selected_profile.get("profile_dir") or ""),
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
            self._refresh_combined_dashboard()
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
            self._refresh_combined_dashboard()

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
            self._refresh_combined_dashboard()

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
                profile_dir=str((self._selected_profile() or {}).get("profile_dir") or ""),
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

        def _on_combined_contact_add_success(self, payload: dict[str, Any]) -> None:
            previous_state = self._load_combined_state()
            if payload.get("job_dir"):
                self.combined_job_dir_var.set(str(payload["job_dir"]))
            summary_text = format_contact_batch_payload(payload)
            self._set_readonly_text(self.combined_output, summary_text)
            transition = combined_contact_add_transition(
                previous_state=previous_state,
                payload=payload,
                session_continuous=bool(self.session_continuous_var.get()),
            )
            tokens, next_cursor, next_step = self._combined_advance_cursor(previous_state)
            self._set_combined_phase(
                str(transition["phase"]),
                input_path=self.combined_input_path_var.get().strip(),
                invite_job_dir=self.combined_job_dir_var.get().strip(),
                session_config_path=self.session_config_path_var.get().strip(),
                step_pattern=self._combined_pattern_text(),
                step_cursor=next_cursor,
                step_label=combined_step_label(next_step),
                last_action=str(transition["last_action"]),
                last_status=str(transition["last_status"]),
                last_summary=summary_text,
                last_invite_status=str(payload.get("status") or "completed").strip().lower() or "completed",
            )
            self.combined_status_var.set(str(transition["status_text"]))
            self._refresh_combined_dashboard()
            if _safe_preview_int(payload.get("selected_users")) > 0 and str(transition.get("phase") or "") != "stopped":
                self._log_event(
                    "telegram_combined_flow",
                    f"Автопереход по шаблону: следующий шаг -> {combined_step_label(next_step)}",
                )
                self._combined_autostart_next_step(next_step)

        def _on_combined_session_success(self, payload: dict[str, Any], runtime_config: Path) -> None:
            summary = format_session_run_payload(payload)
            summary += f"\n\nRuntime config:\n{runtime_config}"
            self._set_readonly_text(self.combined_output, summary)
            run_dir = str(payload.get("run_dir") or "")
            if not run_dir:
                run_info = payload.get("run")
                if isinstance(run_info, dict):
                    run_dir = str(run_info.get("run_dir") or run_info.get("run_id") or "")
            invite_snapshot = None
            job_dir = self.combined_job_dir_var.get().strip()
            if job_dir:
                invite_snapshot = contact_job_snapshot(job_dir)
            transition = combined_session_transition(
                payload=payload,
                invite_snapshot=invite_snapshot,
                session_continuous=bool(self.session_continuous_var.get()),
            )
            current_state = self._load_combined_state()
            tokens, next_cursor, next_step = self._combined_advance_cursor(current_state)
            self._set_combined_phase(
                str(transition["phase"]),
                input_path=self.combined_input_path_var.get().strip(),
                invite_job_dir=self.combined_job_dir_var.get().strip(),
                session_config_path=self.session_config_path_var.get().strip(),
                step_pattern=self._combined_pattern_text(),
                step_cursor=next_cursor,
                step_label=combined_step_label(next_step),
                last_runtime_config_path=str(runtime_config),
                last_action=str(transition["last_action"]),
                last_status=str(transition["last_status"]),
                last_summary=summary,
                last_session_status=str(payload.get("status") or "").strip().lower() or "completed",
                last_session_run_dir=run_dir,
            )
            self.combined_status_var.set(str(transition["status_text"]))
            self._refresh_combined_dashboard()
            if bool(transition.get("auto_start_contact_add")):
                self._log_event(
                    "telegram_combined_flow",
                    f"Автопереход по шаблону: следующий шаг -> {combined_step_label(next_step)}",
                )
                self._combined_autostart_next_step(next_step)

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
