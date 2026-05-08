from __future__ import annotations

from typing import Protocol

from ..models import AccountOption, BrowserTarget, ChatOption, ExportResult, PreflightInfo
from ..services.process_runner import TaskController


class TelegramExecutionAdapter(Protocol):
    key: str
    label: str
    badge: str
    primary: bool

    def connect(self, account: AccountOption, *, launch_browser: bool = True) -> BrowserTarget | None:
        ...

    def list_chats(self, account: AccountOption, target: BrowserTarget) -> tuple[BrowserTarget, list[ChatOption]]:
        ...

    def open_chat(self, account: AccountOption, target: BrowserTarget, chat: ChatOption) -> BrowserTarget:
        ...

    def run_export(
        self,
        account: AccountOption,
        target: BrowserTarget,
        chat: ChatOption,
        output_path,
        emit,
        controller: TaskController | None = None,
        *,
        preset_key: str,
        preset_label: str,
    ) -> ExportResult:
        ...

    def supports_resume(self) -> bool:
        ...

    def matches_target(self, target: BrowserTarget) -> bool:
        ...


class BaseAdapter:
    key = ""
    label = ""
    badge = ""
    primary = False

    def supports_resume(self) -> bool:
        return True
