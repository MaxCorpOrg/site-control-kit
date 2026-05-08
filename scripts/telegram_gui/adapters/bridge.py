from __future__ import annotations

import time
from pathlib import Path
from typing import TYPE_CHECKING, Callable

from .base import BaseAdapter
from ..models import AccountOption, BrowserTarget, ChatOption, ExportResult
from ..services.process_runner import TaskController

if TYPE_CHECKING:
    from ..app import TelegramGuiBackend


class BridgeAdapter(BaseAdapter):
    key = "bridge"
    label = "Telegram Web bridge"
    badge = "Fallback Bridge"
    primary = False

    def __init__(self, backend: "TelegramGuiBackend"):
        self.backend = backend

    def connect(self, account: AccountOption, *, launch_browser: bool = True) -> BrowserTarget | None:
        self.backend._ensure_hub(account.token)
        known_client_ids = {item.get("client_id") for item in self.backend._list_clients(account.token)}
        target = self.backend._resolve_best_client(account.token, known_client_ids=known_client_ids, require_online=True)
        if target is not None:
            self.backend._log_action(f"client_ready bridge client_id={target.client_id} tab_id={target.tab_id}")
        return target

    def list_chats(self, account: AccountOption, target: BrowserTarget) -> tuple[BrowserTarget, list[ChatOption]]:
        refreshed = target
        last_error = ""
        for attempt in range(5):
            if self.backend._is_cdp_target(refreshed):
                return self.backend.fetch_chats(account, refreshed)
            self.backend._wait_for_chat_list_ready(account.token, refreshed.client_id, refreshed.tab_id)
            delivery = self.backend.export_mod._send_command_result(
                server=self.backend.HUB_URL,
                token=account.token,
                client_id=refreshed.client_id,
                tab_id=refreshed.tab_id,
                timeout_sec=12,
                command={"type": "run_script", "script": self.backend.VISIBLE_DIALOGS_SCRIPT},
                raise_on_fail=False,
            )
            if delivery.get("ok"):
                payload = ((delivery.get("data") or {}).get("value") or {}) if isinstance(delivery.get("data"), dict) else {}
                chats = self.backend.normalize_chat_options(payload)
                if chats:
                    self.backend._log_action(f"chats_loaded client_id={refreshed.client_id} count={len(chats)}")
                    return refreshed, chats
                last_error = "Список диалогов пока пустой"
            else:
                last_error = self.backend._format_command_error(delivery.get("error")) or "Не удалось получить список чатов из Telegram Web."
            if attempt < 4:
                time.sleep(0.8)
                refreshed = self.backend.ensure_connected(account, launch_browser=True)
        raise RuntimeError(
            f"{last_error or 'Telegram открыт, но список диалогов не прочитан.'} "
            "Откройте Telegram Web, дождитесь загрузки левой колонки и обновите список."
        )

    def open_chat(self, account: AccountOption, target: BrowserTarget, chat: ChatOption) -> BrowserTarget:
        refreshed = self.backend._refresh_target(account.token, target.client_id, target.tab_id)
        delivery = self.backend.export_mod._send_command_result(
            server=self.backend.HUB_URL,
            token=account.token,
            client_id=refreshed.client_id,
            tab_id=refreshed.tab_id,
            timeout_sec=12,
            command={"type": "navigate", "url": chat.url},
            raise_on_fail=False,
        )
        if not delivery.get("ok"):
            raise RuntimeError(self.backend._format_command_error(delivery.get("error")) or f"Не удалось открыть чат {chat.title}.")
        time.sleep(0.8)
        final_target = self.backend._refresh_target(account.token, refreshed.client_id, refreshed.tab_id)
        self.backend._log_action(f"chat_opened client_id={final_target.client_id} url={chat.url}")
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
        return self.backend._run_export_via_bridge(
            account=account,
            target=target,
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
        return not target.client_id.startswith("tdata:") and not target.client_id.startswith("cdp:")
