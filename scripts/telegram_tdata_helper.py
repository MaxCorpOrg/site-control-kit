#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import re
import signal
import sys
import traceback
from pathlib import Path
from typing import Any

try:
    from opentele.api import UseCurrentSession
    from opentele.td import TDesktop
except ImportError:
    UseCurrentSession = None
    TDesktop = None

try:
    from telethon import utils
except ImportError:
    utils = None

try:
    from telethon.errors.rpcerrorlist import MsgidDecreaseRetryError
except ImportError:
    MsgidDecreaseRetryError = None

try:
    from telethon.tl.functions.messages import CheckChatInviteRequest, ImportChatInviteRequest
except ImportError:
    CheckChatInviteRequest = None
    ImportChatInviteRequest = None


class StopState:
    def __init__(self) -> None:
        self.requested = False

    def request(self) -> None:
        self.requested = True

    def reset(self) -> None:
        self.requested = False


_SIGNAL_STOP_STATE = StopState()
HISTORY_RETRY_LIMIT = 5
HISTORY_RETRY_BASE_DELAY_SEC = 1.0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Telegram tdata helper for site-control-kit GUI.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--tdata", required=True, help="Path to Telegram Desktop tdata directory.")
    common.add_argument("--session", required=True, help="Path to a Telethon session file.")
    common.add_argument("--passcode", default=None, help="Local Telegram Desktop passcode if configured.")

    list_parser = subparsers.add_parser("list-chats", parents=[common], help="List dialogs from imported tdata session.")
    list_parser.add_argument("--limit", type=int, default=200, help="Maximum number of dialogs to list.")

    resolve_parser = subparsers.add_parser("resolve-chat", parents=[common], help="Resolve a public Telegram chat target.")
    resolve_parser.add_argument("--chat", required=True, help="Public chat target: https://t.me/name, @name or peer id.")

    join_parser = subparsers.add_parser("join-invite", parents=[common], help="Join a Telegram chat by invite link.")
    join_parser.add_argument("--invite-link", required=True, help="Telegram invite link like https://t.me/+hash.")

    export_parser = subparsers.add_parser("export-chat", parents=[common], help="Collect usernames from one chat.")
    export_parser.add_argument("--chat-ref", required=True, help="Dialog reference returned by list-chats.")
    export_parser.add_argument(
        "--source",
        choices=("history", "participants", "both"),
        default="both",
        help="Where to collect usernames from.",
    )
    export_parser.add_argument("--participants-limit", type=int, default=0, help="Max participants to scan (0 = no limit).")
    export_parser.add_argument("--history-limit", type=int, default=3000, help="Messages to scan from history (0 = all available).")
    export_parser.add_argument("--progress-every", type=int, default=250, help="Progress line every N scanned messages (0 = disable).")
    export_parser.add_argument("--include-bots", action="store_true", help="Include bot usernames in the result.")
    return parser


def _compact(value: Any) -> str:
    return str(value or "").replace("\n", " ").replace("\r", " ").strip()


def _install_signal_handlers(stop_state: StopState) -> None:
    stop_state.reset()

    def _handler(_signum: int, _frame: Any) -> None:
        stop_state.request()

    for sig in (getattr(signal, "SIGTERM", None), getattr(signal, "SIGINT", None)):
        if sig is None:
            continue
        try:
            signal.signal(sig, _handler)
        except (OSError, RuntimeError, ValueError):
            continue


def _normalize_username(value: str | None) -> str:
    text = _compact(value)
    if not text:
        return "—"
    for pattern in (
        r"https?://t\.me/([A-Za-z0-9_]{5,32})",
        r"t\.me/([A-Za-z0-9_]{5,32})",
        r"@([A-Za-z0-9_]{5,32})",
    ):
        match = re.search(pattern, text, flags=re.I)
        if match:
            candidate = match.group(1)
            if _is_valid_username_candidate(candidate):
                return f"@{candidate}"
    if _is_valid_username_candidate(text):
        return f"@{text}"
    return "—"


def _is_valid_username_candidate(value: str) -> bool:
    text = _compact(value)
    if not text or not re.fullmatch(r"[A-Za-z0-9_]{5,32}", text):
        return False
    return not text.isdigit()


def _peer_id(entity: Any) -> str:
    if utils is not None:
        try:
            return str(utils.get_peer_id(entity))
        except Exception:
            pass
    for attr in ("peer_id", "id", "user_id", "channel_id", "chat_id"):
        value = getattr(entity, attr, None)
        cleaned = str(value or "").strip()
        if cleaned:
            return cleaned
    return ""


def _invite_hash_from_value(value: str | None) -> str:
    text = _compact(value)
    if not text:
        return ""
    for pattern in (
        r"(?:https?://)?t\.me/\+([A-Za-z0-9_-]+)",
        r"(?:https?://)?t\.me/joinchat/([A-Za-z0-9_-]+)",
        r"tg://join\?invite=([A-Za-z0-9_-]+)",
    ):
        match = re.search(pattern, text, flags=re.I)
        if match:
            return _compact(match.group(1))
    if re.fullmatch(r"[A-Za-z0-9_-]{8,128}", text) and not text.lstrip("-").isdigit():
        return text
    return ""


def _public_chat_ref_from_value(value: str | None) -> str:
    text = _compact(value)
    if not text or _invite_hash_from_value(text):
        return ""
    if re.fullmatch(r"-?\d+", text):
        return text
    for pattern in (
        r"(?:https?://)?t\.me/(?!joinchat/|\+)([A-Za-z0-9_]{5,32})(?:[/?].*)?$",
        r"@([A-Za-z0-9_]{5,32})",
    ):
        match = re.search(pattern, text, flags=re.I)
        if match:
            candidate = _compact(match.group(1))
            if _is_valid_username_candidate(candidate):
                return f"@{candidate}"
    candidate = text[1:] if text.startswith("@") else text
    if _is_valid_username_candidate(candidate):
        return f"@{candidate}"
    return ""


def _entity_kind(entity: Any) -> str:
    kind = entity.__class__.__name__.lower()
    if "channel" in kind:
        return "channel"
    if "chat" in kind:
        return "group"
    if "user" in kind:
        return "user"
    return kind or "dialog"


def _dialog_title(dialog: Any) -> str:
    title = _compact(getattr(dialog, "title", None))
    if title:
        return title
    entity = getattr(dialog, "entity", None)
    title = _compact(getattr(entity, "title", None))
    if title:
        return title
    username = _compact(getattr(entity, "username", None))
    if username:
        return username
    return _compact(getattr(entity, "first_name", None)) or "Telegram"


def _chat_item_from_entity(entity: Any, *, title: str = "") -> dict[str, Any]:
    username = _compact(getattr(entity, "username", None))
    display_title = _compact(title) or _compact(getattr(entity, "title", None)) or _compact(getattr(entity, "first_name", None)) or username or "Telegram"
    return {
        "title": display_title,
        "chat_ref": _peer_id(entity) or username or display_title,
        "username": f"@{username}" if username else "",
        "peer_id": _peer_id(entity),
        "subtitle": _entity_kind(entity),
    }


def _resolve_access_state(exc: Exception) -> str:
    name = exc.__class__.__name__
    if name in {
        "UsernameInvalidError",
        "UsernameNotOccupiedError",
        "PeerIdInvalidError",
        "ValueError",
    }:
        return "not_found"
    if name in {
        "InviteHashExpiredError",
        "InviteHashInvalidError",
        "InviteRequestSentError",
    }:
        return "invite_required"
    if name in {
        "ChannelInvalidError",
        "ChannelPrivateError",
        "ChatAdminRequiredError",
        "ChatForbiddenError",
        "UserNotParticipantError",
    }:
        return "resolved_but_no_access"
    return "not_found"


async def _open_client(tdata_path: str, session_path: str, passcode: str | None):
    if TDesktop is None or UseCurrentSession is None:
        raise SystemExit("Missing opentele dependency. Run this helper via the collector venv.")
    tdesk = TDesktop(basePath=tdata_path, passcode=passcode)
    if not tdesk.isLoaded():
        raise SystemExit("Failed to load tdata session.")
    client = await tdesk.ToTelethon(session=session_path, flag=UseCurrentSession)
    await client.connect()
    if not await client.is_user_authorized():
        await client.disconnect()
        raise SystemExit("Imported tdata session is not authorized.")
    return client


async def list_chats(*, tdata_path: str, session_path: str, passcode: str | None, limit: int) -> dict[str, Any]:
    client = await _open_client(tdata_path, session_path, passcode)
    items: list[dict[str, Any]] = []
    try:
        async for dialog in client.iter_dialogs(limit=max(limit, 1)):
            entity = getattr(dialog, "entity", None)
            if entity is None:
                continue
            items.append(_chat_item_from_entity(entity, title=_dialog_title(dialog)))
    finally:
        await client.disconnect()
    return {"ok": True, "items": items}


async def resolve_chat(*, tdata_path: str, session_path: str, passcode: str | None, chat: str) -> dict[str, Any]:
    raw_target = _compact(chat)
    normalized = _public_chat_ref_from_value(raw_target)
    if not normalized:
        access_state = "invite_required" if _invite_hash_from_value(raw_target) else "not_found"
        detail = (
            "Этот target выглядит как invite. Используйте join-invite path."
            if access_state == "invite_required"
            else f"Unsupported Telegram public chat target: {raw_target}"
        )
        return {
            "ok": False,
            "chat": raw_target,
            "access_state": access_state,
            "detail": detail,
        }

    client = await _open_client(tdata_path, session_path, passcode)
    try:
        try:
            entity = await client.get_entity(int(normalized) if normalized.lstrip("-").isdigit() else normalized)
        except Exception as exc:
            return {
                "ok": False,
                "chat": normalized,
                "access_state": _resolve_access_state(exc),
                "detail": _compact(str(exc)) or "Failed to resolve Telegram chat target.",
            }

        item = _chat_item_from_entity(entity)
        access_state = "ok"
        detail = ""
        try:
            async for _msg in client.iter_messages(entity, limit=1):
                break
        except Exception as exc:
            access_state = _resolve_access_state(exc)
            if access_state == "not_found":
                access_state = "resolved_but_no_access"
            detail = _compact(str(exc)) or "Resolved target is not accessible for export."
        return {
            "ok": access_state == "ok",
            "chat": normalized,
            "access_state": access_state,
            "detail": detail,
            "item": item,
        }
    finally:
        await client.disconnect()


async def join_invite(*, tdata_path: str, session_path: str, passcode: str | None, invite_link: str) -> dict[str, Any]:
    if CheckChatInviteRequest is None or ImportChatInviteRequest is None:
        raise SystemExit("Missing Telethon invite dependency. Run this helper via the collector venv.")
    invite_hash = _invite_hash_from_value(invite_link)
    if not invite_hash:
        raise SystemExit(f"Unsupported Telegram invite link: {invite_link}")

    client = await _open_client(tdata_path, session_path, passcode)
    try:
        preview = await client(CheckChatInviteRequest(invite_hash))
        entity = getattr(preview, "chat", None)
        title = _compact(getattr(preview, "title", None))
        already_member = entity is not None
        joined = False
        if entity is None:
            updates = await client(ImportChatInviteRequest(invite_hash))
            joined = True
            chats = list(getattr(updates, "chats", []) or [])
            entity = chats[0] if chats else None
            if entity is None:
                followup = await client(CheckChatInviteRequest(invite_hash))
                entity = getattr(followup, "chat", None)
                if not title:
                    title = _compact(getattr(followup, "title", None))
        if entity is None:
            raise SystemExit("Invite import succeeded, but the joined chat could not be resolved.")
        item = _chat_item_from_entity(entity, title=title)
        return {
            "ok": True,
            "joined": joined,
            "already_member": already_member,
            "invite_hash": invite_hash,
            "item": item,
        }
    finally:
        await client.disconnect()


def _merge_row(rows_by_peer: dict[str, dict[str, str]], row: dict[str, str]) -> None:
    peer_id = str(row.get("peer_id") or "").strip()
    username = str(row.get("username") or "").strip()
    if not peer_id or username in {"", "—"}:
        return
    current = rows_by_peer.get(peer_id)
    if current is None:
        rows_by_peer[peer_id] = row
        return
    if current["username"] == "—" and row["username"] != "—":
        current["username"] = row["username"]
    if current["status"] in {"", "—", "из history"} and row["status"] not in {"", "—"}:
        current["status"] = row["status"]
    if current["role"] in {"", "—"} and row["role"] not in {"", "—"}:
        current["role"] = row["role"]
    if current["name"] in {"", "—"} and row["name"] not in {"", "—"}:
        current["name"] = row["name"]


def _entity_class_name(entity: Any) -> str:
    return entity.__class__.__name__.lower()


def _is_user_entity(entity: Any) -> bool:
    kind = _entity_class_name(entity)
    return "user" in kind and "channel" not in kind and "chat" not in kind


def _is_probable_bot(entity: Any, *, name: str, username: str) -> bool:
    if bool(getattr(entity, "bot", False)):
        return True
    if username != "—" and username.lower().endswith("bot"):
        return True
    return "bot" in name.lower()


def _build_member_row(entity: Any, *, status: str, role: str) -> dict[str, str] | None:
    username = _normalize_username(getattr(entity, "username", None))
    if username == "—":
        return None
    return {
        "peer_id": _peer_id(entity),
        "name": _compact(getattr(entity, "first_name", None) or getattr(entity, "title", None) or getattr(entity, "username", None))
        or "—",
        "username": username,
        "status": status,
        "role": role,
    }


def _stop_requested(stop_state: Any | None) -> bool:
    return bool(getattr(stop_state, "requested", False))


def _emit_progress(
    chat_ref: str,
    *,
    messages_scanned: int,
    usernames_found: int,
    stage: str = "",
    interrupted: bool = False,
    done: bool = False,
) -> None:
    parts = [
        "PROGRESS",
        f"chat={chat_ref}",
        f"messages={int(messages_scanned)}",
        f"usernames={int(usernames_found)}",
    ]
    if stage:
        parts.append(f"stage={stage}")
    if interrupted:
        parts.append("interrupted=1")
    if done:
        parts.append("done=1")
    print(" ".join(parts), file=sys.stderr, flush=True)


def _message_id(message: Any) -> int:
    try:
        value = int(getattr(message, "id", 0) or 0)
    except (TypeError, ValueError):
        return 0
    return value if value > 0 else 0


def _is_msgid_decrease_retry_error(exc: Exception) -> bool:
    if MsgidDecreaseRetryError is not None and isinstance(exc, MsgidDecreaseRetryError):
        return True
    return exc.__class__.__name__ == "MsgidDecreaseRetryError"


def _emit_history_retry(chat_ref: str, *, retry: int, offset_id: int, remaining: int | None, exc: Exception) -> None:
    parts = [
        "RETRY",
        f"chat={chat_ref}",
        f"retry={retry}",
        f"reason={exc.__class__.__name__}",
    ]
    if offset_id > 0:
        parts.append(f"offset_id={offset_id}")
    if remaining is not None:
        parts.append(f"remaining={max(int(remaining), 0)}")
    detail = _compact(str(exc))
    if detail:
        parts.append(f"detail={detail}")
    print(" ".join(parts), file=sys.stderr, flush=True)


async def _iter_history_messages_with_retry(
    client: Any,
    entity: Any,
    *,
    chat_ref: str,
    message_limit: int | None,
) -> Any:
    remaining = message_limit
    offset_id = 0
    retry_count = 0
    while True:
        iter_kwargs: dict[str, Any] = {}
        if remaining is not None:
            iter_kwargs["limit"] = remaining
        if offset_id > 0:
            iter_kwargs["offset_id"] = offset_id
        try:
            async for msg in client.iter_messages(entity, **iter_kwargs):
                retry_count = 0
                msg_id = _message_id(msg)
                if msg_id > 0:
                    offset_id = msg_id
                if remaining is not None:
                    remaining -= 1
                yield msg
                if remaining is not None and remaining <= 0:
                    return
            return
        except Exception as exc:
            if not _is_msgid_decrease_retry_error(exc):
                raise
            retry_count += 1
            if retry_count > HISTORY_RETRY_LIMIT:
                raise
            _emit_history_retry(
                chat_ref,
                retry=retry_count,
                offset_id=offset_id,
                remaining=remaining,
                exc=exc,
            )
            await asyncio.sleep(min(HISTORY_RETRY_BASE_DELAY_SEC * retry_count, 5.0))


async def _resolve_message_sender(client: Any, sender_id: int | None, sender: Any, sender_cache: dict[int, Any | None]) -> Any | None:
    if sender_id is None:
        return None
    if sender_id in sender_cache:
        return sender_cache[sender_id]
    resolved = sender
    if resolved is None:
        try:
            resolved = await client.get_entity(sender_id)
        except Exception:
            resolved = None
    sender_cache[sender_id] = resolved
    return resolved


async def export_chat(
    *,
    tdata_path: str,
    session_path: str,
    passcode: str | None,
    chat_ref: str,
    source: str,
    participants_limit: int,
    history_limit: int,
    progress_every: int,
    include_bots: bool,
    stop_state: Any | None = None,
) -> dict[str, Any]:
    client = await _open_client(tdata_path, session_path, passcode)
    rows_by_peer: dict[str, dict[str, str]] = {}
    sender_cache: dict[int, Any | None] = {}
    interrupted = False
    stats = {
        "participants_scanned": 0,
        "history_messages_scanned": 0,
        "history_usernames_kept": 0,
        "participants_usernames_kept": 0,
    }
    try:
        entity = await client.get_entity(int(chat_ref) if str(chat_ref).lstrip("-").isdigit() else chat_ref)

        if source in {"both", "participants"}:
            scanned = 0
            kept = 0
            async for user in client.iter_participants(entity, aggressive=True):
                if _stop_requested(stop_state):
                    interrupted = True
                    break
                scanned += 1
                if not _is_user_entity(user):
                    if participants_limit > 0 and scanned >= participants_limit:
                        break
                    continue
                row = _build_member_row(
                    user,
                    status="из participants",
                    role="bot" if bool(getattr(user, "bot", False)) else "member",
                )
                if row is None:
                    if participants_limit > 0 and scanned >= participants_limit:
                        break
                    continue
                if not include_bots and _is_probable_bot(user, name=row["name"], username=row["username"]):
                    if participants_limit > 0 and scanned >= participants_limit:
                        break
                    continue
                _merge_row(rows_by_peer, row)
                kept += 1
                if participants_limit > 0 and scanned >= participants_limit:
                    break
            stats["participants_scanned"] = scanned
            stats["participants_usernames_kept"] = kept

        if source in {"both", "history"} and not interrupted:
            message_limit = None if history_limit <= 0 else history_limit
            kept = 0
            _emit_progress(chat_ref, messages_scanned=0, usernames_found=len(rows_by_peer), stage="start")
            async for msg in _iter_history_messages_with_retry(
                client,
                entity,
                chat_ref=chat_ref,
                message_limit=message_limit,
            ):
                if _stop_requested(stop_state):
                    interrupted = True
                    break
                stats["history_messages_scanned"] += 1
                sender_id = getattr(msg, "sender_id", None)
                sender = await _resolve_message_sender(client, sender_id, getattr(msg, "sender", None), sender_cache)
                if sender is None or not _is_user_entity(sender):
                    continue
                row = _build_member_row(
                    sender,
                    status="из history",
                    role="bot" if bool(getattr(sender, "bot", False)) else "author",
                )
                if row is None:
                    if progress_every > 0 and stats["history_messages_scanned"] % progress_every == 0:
                        _emit_progress(
                            chat_ref,
                            messages_scanned=stats["history_messages_scanned"],
                            usernames_found=len(rows_by_peer),
                        )
                    continue
                if not include_bots and _is_probable_bot(sender, name=row["name"], username=row["username"]):
                    if progress_every > 0 and stats["history_messages_scanned"] % progress_every == 0:
                        _emit_progress(
                            chat_ref,
                            messages_scanned=stats["history_messages_scanned"],
                            usernames_found=len(rows_by_peer),
                        )
                    continue
                _merge_row(rows_by_peer, row)
                kept += 1
                if progress_every > 0 and stats["history_messages_scanned"] % progress_every == 0:
                    _emit_progress(
                        chat_ref,
                        messages_scanned=stats["history_messages_scanned"],
                        usernames_found=len(rows_by_peer),
                    )
            stats["history_usernames_kept"] = kept
            _emit_progress(
                chat_ref,
                messages_scanned=stats["history_messages_scanned"],
                usernames_found=len(rows_by_peer),
                interrupted=interrupted,
                done=True,
            )
    finally:
        await client.disconnect()

    rows = list(rows_by_peer.values())
    rows.sort(key=lambda item: (item["username"] == "—", item["name"].lower(), item["peer_id"]))
    usernames = sorted({item["username"] for item in rows if item["username"] != "—"}, key=str.lower)
    stats["interrupted"] = 1 if interrupted else 0
    return {"ok": True, "rows": rows, "usernames": usernames, "stats": stats, "interrupted": interrupted}


async def _async_main(args: argparse.Namespace) -> dict[str, Any]:
    session_path = str(Path(args.session).expanduser().resolve())
    tdata_path = str(Path(args.tdata).expanduser().resolve())
    if args.command == "list-chats":
        return await list_chats(
            tdata_path=tdata_path,
            session_path=session_path,
            passcode=args.passcode,
            limit=int(args.limit),
        )
    if args.command == "resolve-chat":
        return await resolve_chat(
            tdata_path=tdata_path,
            session_path=session_path,
            passcode=args.passcode,
            chat=str(args.chat),
        )
    if args.command == "join-invite":
        return await join_invite(
            tdata_path=tdata_path,
            session_path=session_path,
            passcode=args.passcode,
            invite_link=str(args.invite_link),
        )
    if args.command == "export-chat":
        return await export_chat(
            tdata_path=tdata_path,
            session_path=session_path,
            passcode=args.passcode,
            chat_ref=str(args.chat_ref),
            source=str(args.source),
            participants_limit=int(args.participants_limit),
            history_limit=int(args.history_limit),
            progress_every=int(args.progress_every),
            include_bots=bool(args.include_bots),
            stop_state=_SIGNAL_STOP_STATE,
        )
    raise SystemExit(f"Unsupported command: {args.command}")


def main() -> int:
    args = build_parser().parse_args()
    _install_signal_handlers(_SIGNAL_STOP_STATE)
    try:
        payload = asyncio.run(_async_main(args))
    except SystemExit:
        raise
    except Exception:
        traceback.print_exc()
        return 1
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
