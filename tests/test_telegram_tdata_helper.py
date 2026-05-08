from __future__ import annotations

import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from scripts import telegram_tdata_helper as mod


class FakeUser:
    def __init__(self, peer_id: int, *, username: str | None, first_name: str = "User", bot: bool = False) -> None:
        self.id = peer_id
        self.peer_id = peer_id
        self.username = username
        self.first_name = first_name
        self.bot = bot


class FakeChannel:
    def __init__(self, peer_id: int, *, username: str | None, title: str = "Channel") -> None:
        self.id = peer_id
        self.peer_id = peer_id
        self.username = username
        self.title = title
        self.bot = False


class FakeMessage:
    def __init__(self, sender_id: int | None, sender: object | None, *, msg_id: int | None = None) -> None:
        self.sender_id = sender_id
        self.sender = sender
        self.id = msg_id if msg_id is not None else int(sender_id or 0)


class FakeClient:
    def __init__(self, *, messages: list[FakeMessage], entity_by_id: dict[int, object]) -> None:
        self._messages = messages
        self._entity_by_id = entity_by_id
        self.participants_called = False
        self.disconnected = False

    async def get_entity(self, ref: object) -> object:
        if isinstance(ref, int) and ref in self._entity_by_id:
            return self._entity_by_id[ref]
        return object()

    def iter_messages(self, _entity: object, limit: int | None = None):
        async def generator():
            count = 0
            for item in self._messages:
                if limit is not None and count >= limit:
                    break
                count += 1
                yield item

        return generator()

    def iter_participants(self, _entity: object, aggressive: bool = True):
        self.participants_called = True

        async def generator():
            if False:
                yield aggressive

        return generator()

    async def disconnect(self) -> None:
        self.disconnected = True


class FakeResolveError(Exception):
    pass


class TelegramTdataHelperTests(unittest.TestCase):
    def test_normalize_username_rejects_numeric_and_short_values(self) -> None:
        self.assertEqual(mod._normalize_username("Bychkov_AA"), "@Bychkov_AA")
        self.assertEqual(mod._normalize_username("@1291639730"), "—")
        self.assertEqual(mod._normalize_username("bot"), "—")

    def test_invite_hash_from_value_supports_t_me_plus_links(self) -> None:
        self.assertEqual(mod._invite_hash_from_value("http://t.me/+6FMgmFJCh0I4M2Yy"), "6FMgmFJCh0I4M2Yy")
        self.assertEqual(mod._invite_hash_from_value("https://t.me/joinchat/AbC_123-x"), "AbC_123-x")
        self.assertEqual(mod._invite_hash_from_value("tg://join?invite=AbC_123-x"), "AbC_123-x")

    def test_public_chat_ref_from_value_supports_public_links_and_peer_ids(self) -> None:
        self.assertEqual(mod._public_chat_ref_from_value("https://t.me/cosmetologna"), "@cosmetologna")
        self.assertEqual(mod._public_chat_ref_from_value("@cosmetologna"), "@cosmetologna")
        self.assertEqual(mod._public_chat_ref_from_value("-1002269737802"), "-1002269737802")
        self.assertEqual(mod._public_chat_ref_from_value("https://t.me/+6FMgmFJCh0I4M2Yy"), "")

    def test_join_invite_returns_chat_payload_when_already_member(self) -> None:
        class InviteClient:
            def __init__(self) -> None:
                self.disconnected = False

            async def __call__(self, request: object) -> object:
                if getattr(request, "kind", "") == "check":
                    return SimpleNamespace(
                        chat=FakeChannel(-1001909598727, username="cosmochatrussia", title="Invite Chat"),
                        title="Invite Chat",
                    )
                raise AssertionError(f"Unexpected request: {request!r}")

            async def disconnect(self) -> None:
                self.disconnected = True

        fake_client = InviteClient()

        async def fake_open_client(*_args, **_kwargs):
            return fake_client

        with (
            patch.object(mod, "_open_client", side_effect=fake_open_client),
            patch.object(mod, "CheckChatInviteRequest", side_effect=lambda invite_hash: SimpleNamespace(kind="check", invite_hash=invite_hash)),
            patch.object(mod, "ImportChatInviteRequest", side_effect=lambda invite_hash: SimpleNamespace(kind="import", invite_hash=invite_hash)),
        ):
            payload = asyncio.run(
                mod.join_invite(
                    tdata_path="/tmp/tdata",
                    session_path="/tmp/session",
                    passcode=None,
                    invite_link="https://t.me/+6FMgmFJCh0I4M2Yy",
                )
            )

        self.assertTrue(payload["ok"])
        self.assertFalse(payload["joined"])
        self.assertTrue(payload["already_member"])
        self.assertEqual(payload["invite_hash"], "6FMgmFJCh0I4M2Yy")
        self.assertEqual(payload["item"]["title"], "Invite Chat")
        self.assertEqual(payload["item"]["peer_id"], "-1001909598727")
        self.assertTrue(fake_client.disconnected)

    def test_resolve_chat_returns_public_chat_payload(self) -> None:
        class ResolveClient:
            def __init__(self) -> None:
                self.disconnected = False

            async def get_entity(self, ref: object) -> object:
                self.last_ref = ref
                return FakeChannel(-1002269737802, username="cosmetologna", title="Косметолог на миллион")

            def iter_messages(self, _entity: object, limit: int | None = None):
                async def generator():
                    if limit != 0:
                        yield FakeMessage(None, None)

                return generator()

            async def disconnect(self) -> None:
                self.disconnected = True

        fake_client = ResolveClient()

        async def fake_open_client(*_args, **_kwargs):
            return fake_client

        with patch.object(mod, "_open_client", side_effect=fake_open_client):
            payload = asyncio.run(
                mod.resolve_chat(
                    tdata_path="/tmp/tdata",
                    session_path="/tmp/session",
                    passcode=None,
                    chat="https://t.me/cosmetologna",
                )
            )

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["chat"], "@cosmetologna")
        self.assertEqual(payload["access_state"], "ok")
        self.assertEqual(payload["item"]["title"], "Косметолог на миллион")
        self.assertEqual(payload["item"]["peer_id"], "-1002269737802")
        self.assertEqual(payload["item"]["username"], "@cosmetologna")
        self.assertTrue(fake_client.disconnected)

    def test_resolve_chat_returns_not_found_for_unknown_public_target(self) -> None:
        class UsernameNotOccupiedError(FakeResolveError):
            pass

        class ResolveClient:
            def __init__(self) -> None:
                self.disconnected = False

            async def get_entity(self, _ref: object) -> object:
                raise UsernameNotOccupiedError("missing")

            async def disconnect(self) -> None:
                self.disconnected = True

        fake_client = ResolveClient()

        async def fake_open_client(*_args, **_kwargs):
            return fake_client

        with patch.object(mod, "_open_client", side_effect=fake_open_client):
            payload = asyncio.run(
                mod.resolve_chat(
                    tdata_path="/tmp/tdata",
                    session_path="/tmp/session",
                    passcode=None,
                    chat="@missingchat",
                )
            )

        self.assertFalse(payload["ok"])
        self.assertEqual(payload["access_state"], "not_found")
        self.assertTrue(fake_client.disconnected)

    def test_resolve_chat_reports_resolved_but_no_access(self) -> None:
        class ChannelPrivateError(FakeResolveError):
            pass

        class ResolveClient:
            def __init__(self) -> None:
                self.disconnected = False

            async def get_entity(self, _ref: object) -> object:
                return FakeChannel(-1001555954026, username="privatechat", title="Private Chat")

            def iter_messages(self, _entity: object, limit: int | None = None):
                async def generator():
                    raise ChannelPrivateError("forbidden")
                    if limit == -1:  # pragma: no cover
                        yield None

                return generator()

            async def disconnect(self) -> None:
                self.disconnected = True

        fake_client = ResolveClient()

        async def fake_open_client(*_args, **_kwargs):
            return fake_client

        with patch.object(mod, "_open_client", side_effect=fake_open_client):
            payload = asyncio.run(
                mod.resolve_chat(
                    tdata_path="/tmp/tdata",
                    session_path="/tmp/session",
                    passcode=None,
                    chat="@privatechat",
                )
            )

        self.assertFalse(payload["ok"])
        self.assertEqual(payload["access_state"], "resolved_but_no_access")
        self.assertEqual(payload["item"]["peer_id"], "-1001555954026")
        self.assertTrue(fake_client.disconnected)

    def test_export_chat_history_only_keeps_human_message_authors(self) -> None:
        fake_client = FakeClient(
            messages=[
                FakeMessage(11, FakeUser(11, username="human_user", first_name="Human")),
                FakeMessage(12, FakeUser(12, username="alerthelperbot", first_name="Alert", bot=True)),
                FakeMessage(13, None),
                FakeMessage(14, FakeChannel(14, username="channelpost", title="Channel Post")),
                FakeMessage(15, FakeUser(15, username=None, first_name="NoUsername")),
            ],
            entity_by_id={
                13: FakeUser(13, username="resolved_person", first_name="Resolved"),
            },
        )

        async def fake_open_client(*_args, **_kwargs):
            return fake_client

        with patch.object(mod, "_open_client", side_effect=fake_open_client):
            payload = asyncio.run(
                mod.export_chat(
                    tdata_path="/tmp/tdata",
                    session_path="/tmp/session",
                    passcode=None,
                    chat_ref="-1001",
                    source="history",
                    participants_limit=0,
                    history_limit=0,
                    progress_every=0,
                    include_bots=False,
                )
            )

        self.assertEqual([row["username"] for row in payload["rows"]], ["@human_user", "@resolved_person"])
        self.assertEqual(payload["usernames"], ["@human_user", "@resolved_person"])
        self.assertEqual(payload["stats"]["history_messages_scanned"], 5)
        self.assertEqual(payload["stats"]["participants_scanned"], 0)
        self.assertEqual(payload["stats"]["history_usernames_kept"], 2)
        self.assertFalse(fake_client.participants_called)
        self.assertTrue(fake_client.disconnected)

    def test_export_chat_returns_partial_rows_when_stop_requested(self) -> None:
        stop_state = mod.StopState()

        class InterruptingClient(FakeClient):
            def iter_messages(self, _entity: object, limit: int | None = None):
                async def generator():
                    yield FakeMessage(11, FakeUser(11, username="human_user", first_name="Human"))
                    stop_state.request()
                    yield FakeMessage(12, FakeUser(12, username="later_user", first_name="Later"))

                return generator()

        fake_client = InterruptingClient(messages=[], entity_by_id={})

        async def fake_open_client(*_args, **_kwargs):
            return fake_client

        with patch.object(mod, "_open_client", side_effect=fake_open_client):
            payload = asyncio.run(
                mod.export_chat(
                    tdata_path="/tmp/tdata",
                    session_path="/tmp/session",
                    passcode=None,
                    chat_ref="-1001",
                    source="history",
                    participants_limit=0,
                    history_limit=0,
                    progress_every=0,
                    include_bots=False,
                    stop_state=stop_state,
                )
            )

        self.assertTrue(payload["interrupted"])
        self.assertEqual(payload["stats"]["interrupted"], 1)
        self.assertEqual(payload["stats"]["history_messages_scanned"], 1)
        self.assertEqual([row["username"] for row in payload["rows"]], ["@human_user"])
        self.assertTrue(fake_client.disconnected)

    def test_export_chat_retries_msgid_decrease_and_resumes_from_last_message(self) -> None:
        class MsgidDecreaseRetryError(FakeResolveError):
            pass

        class RetryingClient(FakeClient):
            def __init__(self) -> None:
                super().__init__(
                    messages=[],
                    entity_by_id={
                        11: FakeUser(11, username="first_user", first_name="First"),
                        12: FakeUser(12, username="second_user", first_name="Second"),
                        13: FakeUser(13, username="third_user", first_name="Third"),
                    },
                )
                self.calls: list[tuple[int | None, int]] = []

            def iter_messages(self, _entity: object, limit: int | None = None, offset_id: int = 0):
                self.calls.append((limit, offset_id))

                async def generator():
                    if offset_id == 0:
                        yield FakeMessage(11, None, msg_id=300)
                        yield FakeMessage(12, None, msg_id=299)
                        raise MsgidDecreaseRetryError("retry with lower message id")
                    if offset_id == 299:
                        yield FakeMessage(13, None, msg_id=298)
                        return
                    raise AssertionError(f"Unexpected offset_id: {offset_id}")

                return generator()

        fake_client = RetryingClient()

        async def fake_open_client(*_args, **_kwargs):
            return fake_client

        async def fake_sleep(_delay: float) -> None:
            return None

        with (
            patch.object(mod, "_open_client", side_effect=fake_open_client),
            patch.object(mod.asyncio, "sleep", side_effect=fake_sleep),
        ):
            payload = asyncio.run(
                mod.export_chat(
                    tdata_path="/tmp/tdata",
                    session_path="/tmp/session",
                    passcode=None,
                    chat_ref="-1001",
                    source="history",
                    participants_limit=0,
                    history_limit=0,
                    progress_every=0,
                    include_bots=False,
                )
            )

        self.assertEqual(payload["stats"]["history_messages_scanned"], 3)
        self.assertEqual(payload["stats"]["history_usernames_kept"], 3)
        self.assertEqual(
            [row["username"] for row in payload["rows"]],
            ["@first_user", "@second_user", "@third_user"],
        )
        self.assertEqual(fake_client.calls, [(None, 0), (None, 299)])
        self.assertTrue(fake_client.disconnected)


if __name__ == "__main__":
    unittest.main()
