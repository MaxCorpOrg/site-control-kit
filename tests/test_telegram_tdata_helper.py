from __future__ import annotations

import asyncio
import unittest
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
    def __init__(self, sender_id: int | None, sender: object | None) -> None:
        self.sender_id = sender_id
        self.sender = sender


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


class TelegramTdataHelperTests(unittest.TestCase):
    def test_normalize_username_rejects_numeric_and_short_values(self) -> None:
        self.assertEqual(mod._normalize_username("Bychkov_AA"), "@Bychkov_AA")
        self.assertEqual(mod._normalize_username("@1291639730"), "—")
        self.assertEqual(mod._normalize_username("bot"), "—")

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


if __name__ == "__main__":
    unittest.main()
