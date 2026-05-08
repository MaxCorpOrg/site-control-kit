from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Iterable

from ..models import (
    FallbackReadiness,
    PortableProfileStatus,
    PortableRuntimeState,
    PortableSourceInfo,
    PreflightInfo,
    PreflightStatus,
    WorkspaceHealth,
)


class PreflightService:
    def __init__(self, *, workspace_root: Path, default_token: str):
        self.workspace_root = workspace_root.expanduser()
        self.default_token = str(default_token or "")

    def collect_workspace_health(
        self,
        *,
        runtime_dir: Path,
        logs_dir: Path,
        helper_available: bool,
        collector_python_available: bool,
        node_available: bool,
        hub_reachable: bool,
        stale_runtime_files: int = 0,
        warning: str = "",
    ) -> WorkspaceHealth:
        return WorkspaceHealth(
            workspace_writable=_path_writable(self.workspace_root),
            runtime_writable=_path_writable(runtime_dir),
            logs_writable=_path_writable(logs_dir),
            helper_available=helper_available,
            collector_python_available=collector_python_available,
            node_available=node_available,
            hub_reachable=hub_reachable,
            stale_runtime_files=stale_runtime_files,
            warning=warning,
        )

    def build(
        self,
        *,
        surface_key: str,
        surface_label: str,
        surface_badge: str,
        surface_reason: str,
        is_primary: bool,
        tdata_ready: bool,
        helper_ready: bool,
        output_path: Path | None,
        preset_key: str,
        preset_label: str,
        history_limit: str,
        timeout_sec: int | None,
        resume_available: bool,
        token: str,
        token_source: str,
        workspace_health: WorkspaceHealth,
        connection_label: str,
        hub_token_status: str = "",
        hub_token_detail: str = "",
        hub_restart_available: bool = False,
        fallback_bridge: FallbackReadiness | None = None,
        fallback_cdp: FallbackReadiness | None = None,
        portable_source: PortableSourceInfo | None = None,
        portable_runtime: PortableRuntimeState | None = None,
        portable_profile: PortableProfileStatus | None = None,
        notes: Iterable[str] = (),
    ) -> PreflightInfo:
        security_mode, security_state = self.security_mode(token)
        security_detail = self.security_detail(
            token=token,
            token_source=token_source,
            hub_token_status=hub_token_status,
            hub_token_detail=hub_token_detail,
        )
        timeout_text = "unlimited" if timeout_sec is None else f"{timeout_sec}s"
        if surface_key == "profile_missing":
            surface_state = "blocked"
        elif surface_key == "pending":
            surface_state = "pending"
        elif tdata_ready and helper_ready:
            surface_state = "ok"
        elif surface_key == "tdata":
            surface_state = "blocked"
        elif fallback_bridge is not None and fallback_bridge.state == "pending" and fallback_cdp is not None and fallback_cdp.state == "pending":
            surface_state = "pending"
        else:
            surface_state = "warning" if helper_ready else "blocked"
        hub_state = "ok" if workspace_health.hub_reachable else ("pending" if hub_token_status == "pending" else ("warning" if is_primary else "blocked"))
        statuses = (
            PreflightStatus(
                key="hub",
                label="Hub",
                state=hub_state,
                detail=connection_label,
            ),
            PreflightStatus(
                key="surface",
                label="tdata/helper",
                state=surface_state,
                detail=surface_reason or (
                    "tdata primary surface доступен." if tdata_ready and helper_ready else "GUI будет использовать fallback surface."
                ),
            ),
            PreflightStatus(
                key="output",
                label="Output path",
                state="ok" if _output_path_ready(output_path) else "blocked",
                detail=str(output_path) if output_path else "Файл результата ещё не выбран.",
            ),
            PreflightStatus(
                key="preset",
                label="Preset",
                state="ok",
                detail=f"{preset_label} | history_limit={history_limit} | timeout={timeout_text}",
            ),
            PreflightStatus(
                key="security",
                label="Security mode",
                state=security_state,
                detail=security_mode,
            ),
        )
        return PreflightInfo(
            surface_key=surface_key,
            surface_label=surface_label,
            surface_badge=surface_badge,
            is_primary=is_primary,
            tdata_ready=tdata_ready,
            helper_ready=helper_ready,
            output_path=output_path,
            preset_key=preset_key,
            preset_label=preset_label,
            history_limit=history_limit,
            timeout_sec=timeout_sec,
            resume_available=resume_available,
            notes=tuple(notes),
            statuses=statuses,
            security_mode=security_mode,
            security_state=security_state,
            workspace_health=workspace_health,
            surface_reason=surface_reason,
            security_token_source=token_source,
            security_detail=security_detail,
            security_attention_required=security_state != "ok" or hub_token_status in {"owned_mismatch", "foreign_mismatch", "error"},
            security_setup_available=security_state != "ok",
            security_setup_label="Настроить secure token" if security_state != "ok" else "",
            security_restart_available=hub_restart_available,
            security_restart_label="Перезапустить hub этим токеном" if hub_restart_available else "",
            fallback_bridge=fallback_bridge,
            fallback_cdp=fallback_cdp,
            portable_source=portable_source,
            portable_runtime=portable_runtime,
            portable_profile=portable_profile,
        )

    def security_mode(self, token: str) -> tuple[str, str]:
        value = str(token or "").strip()
        if not value:
            return "No token configured", "blocked"
        if value == self.default_token:
            return "Insecure local token", "warning"
        return "Local secure token", "ok"

    def security_detail(
        self,
        *,
        token: str,
        token_source: str,
        hub_token_status: str,
        hub_token_detail: str,
    ) -> str:
        mode, _state = self.security_mode(token)
        source = str(token_source or "").strip() or "missing"
        parts: list[str] = []
        if mode == "Local secure token":
            if source == "secret_ref":
                parts.append("Токен хранится в registry secret store и используется как основной local source.")
            elif source == "slot_key":
                parts.append("Токен читается из legacy slot key. Перенесите его в registry secret store.")
            else:
                parts.append("Локальный токен настроен.")
        elif mode == "Insecure local token":
            if source == "secret_ref":
                parts.append("Токен хранится в secret store, но совпадает с quickstart default и остаётся insecure.")
            elif source == "slot_key":
                parts.append("Профиль использует legacy slot token. Сохраните отдельный secure token в registry.")
            else:
                parts.append("Профиль работает через quickstart fallback. Сохраните отдельный secure token в registry.")
        else:
            parts.append("У профиля нет рабочего токена. Сохраните secure token в registry/secrets.")
        if hub_token_detail:
            parts.append(hub_token_detail)
        elif hub_token_status == "owned_mismatch":
            parts.append("Hub уже запущен этим GUI с другим токеном.")
        elif hub_token_status == "foreign_mismatch":
            parts.append("На :8765 уже живёт внешний hub/process с другим токеном.")
        return " ".join(part for part in parts if part)


def _path_writable(path: Path) -> bool:
    candidate = path.expanduser()
    try:
        candidate.mkdir(parents=True, exist_ok=True)
    except OSError:
        return False
    return os.access(candidate, os.W_OK)


def _output_path_ready(path: Path | None) -> bool:
    if path is None:
        return False
    try:
        path.expanduser().parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        return False
    return os.access(path.expanduser().parent, os.W_OK)
