from __future__ import annotations

import time
from pathlib import Path
from typing import TYPE_CHECKING, Callable

from .base import BaseAdapter
from ..models import AccountOption, BrowserTarget, ChatOption, ExportResult
from ..services.process_runner import TaskController

if TYPE_CHECKING:
    from ..backend import TelegramGuiBackend


class CdpAdapter(BaseAdapter):
    key = "cdp"
    label = "Chrome profile direct"
    badge = "Fallback CDP"
    primary = False

    def __init__(self, backend: "TelegramGuiBackend"):
        self.backend = backend

    def connect(self, account: AccountOption, *, launch_browser: bool = True) -> BrowserTarget | None:
        profile_dir = self.backend.resolve_profile_dir(account.profile_source)
        target = self.backend._ensure_cdp_target(profile_dir, launch_browser=launch_browser)
        if target is not None:
            self.backend._log_action(f"client_ready cdp client_id={target.client_id} tab_id={target.tab_id}")
        return target

    def list_chats(self, account: AccountOption, target: BrowserTarget) -> tuple[BrowserTarget, list[ChatOption]]:
        port = self.backend._cdp_port_from_target(target)
        if port is None:
            raise RuntimeError("CDP target is invalid.")
        payload = self.backend._run_cdp_helper(
            "list-chats",
            port=port,
            timeout_sec=50,
            extra_args=["--url", self.backend.TELEGRAM_WEB_URL, "--timeout-ms", "45000"],
        )
        if payload.get("auth_required"):
            raise RuntimeError("В выбранном профиле Telegram не залогинен. Откройте Telegram и выполните вход.")
        chats = self.backend.normalize_chat_options(payload)
        if not chats:
            raise RuntimeError("Telegram открыт, но список чатов пуст. Дождитесь полной загрузки левой колонки и обновите список.")
        refreshed = BrowserTarget(
            client_id=target.client_id,
            tab_id=target.tab_id,
            tab_title=self.backend._clean_tab_title(str(payload.get("current_title") or "Telegram")),
            tab_url=str(payload.get("current_url") or self.backend.TELEGRAM_WEB_URL),
        )
        self.backend._log_action(f"chats_loaded cdp port={port} count={len(chats)}")
        return refreshed, chats

    def open_chat(self, account: AccountOption, target: BrowserTarget, chat: ChatOption) -> BrowserTarget:
        port = self.backend._cdp_port_from_target(target)
        if port is None:
            raise RuntimeError("CDP target is invalid.")
        payload = self.backend._run_cdp_helper(
            "open-chat",
            port=port,
            timeout_sec=40,
            extra_args=["--url", chat.url, "--timeout-ms", "30000"],
        )
        final_target = BrowserTarget(
            client_id=target.client_id,
            tab_id=target.tab_id,
            tab_title=self.backend._clean_tab_title(str(payload.get("current_title") or chat.title)),
            tab_url=str(payload.get("current_url") or chat.url),
        )
        self.backend._log_action(f"chat_opened cdp port={port} url={chat.url}")
        return final_target

    def run_export(
        self,
        account: AccountOption,
        target: BrowserTarget,
        chat: ChatOption,
        output_path: Path,
        emit: Callable[[str], None],
        controller: TaskController | None = None,
        *,
        preset_key: str,
        preset_label: str,
    ) -> ExportResult:
        port = self.backend._cdp_port_from_target(target)
        if port is None:
            raise RuntimeError("CDP target is invalid.")
        return self.backend._run_export_via_cdp(
            port=port,
            chat=chat,
            output_path=output_path,
            emit=emit,
            controller=controller,
            preset_key=preset_key,
            preset_label=preset_label,
            surface_key=self.key,
            surface_label=self.label,
            surface_badge=self.badge,
        )

    def matches_target(self, target: BrowserTarget) -> bool:
        return self.backend._is_cdp_target(target)
