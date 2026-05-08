from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Callable

from .base import BaseAdapter
from ..models import AccountOption, BrowserTarget, ChatOption, ExportResult
from ..services.process_runner import TaskController

if TYPE_CHECKING:
    from ..app import TelegramGuiBackend


class TdataAdapter(BaseAdapter):
    key = "tdata"
    label = "Telegram Desktop tdata"
    badge = "Primary tdata"
    primary = True

    def __init__(self, backend: "TelegramGuiBackend"):
        self.backend = backend

    def connect(self, account: AccountOption, *, launch_browser: bool = True) -> BrowserTarget | None:
        profile_dir = self.backend.resolve_profile_dir(account.profile_source)
        target = self.backend._ensure_tdata_target(profile_dir, launch_browser=launch_browser, account=account)
        if target is not None:
            self.backend._log_action(f"client_ready tdata client_id={target.client_id}")
        return target

    def list_chats(self, account: AccountOption, target: BrowserTarget) -> tuple[BrowserTarget, list[ChatOption]]:
        tdata_dir = self.backend._tdata_dir_from_target(target)
        if tdata_dir is None:
            raise RuntimeError("tdata target is invalid.")
        payload = self.backend._run_tdata_helper("list-chats", tdata_dir=tdata_dir, extra_args=["--limit", "200"])
        chats = self.backend.normalize_tdata_chat_options(payload)
        if not chats:
            raise RuntimeError("В tdata-сессии не удалось прочитать список диалогов.")
        refreshed = BrowserTarget(
            client_id=target.client_id,
            tab_id=target.tab_id,
            tab_title="Telegram Desktop",
            tab_url=str(tdata_dir),
        )
        self.backend._log_action(f"chats_loaded tdata dir={tdata_dir} count={len(chats)}")
        return refreshed, chats

    def open_chat(self, account: AccountOption, target: BrowserTarget, chat: ChatOption) -> BrowserTarget:
        self.backend._log_action(f"chat_opened tdata direct chat_ref={chat.fragment}")
        return target

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
        tdata_dir = self.backend._tdata_dir_from_target(target)
        if tdata_dir is None:
            raise RuntimeError("tdata target is invalid.")
        return self.backend._run_export_via_tdata(
            tdata_dir=tdata_dir,
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
        return self.backend._is_tdata_target(target)
