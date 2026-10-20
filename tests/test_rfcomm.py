import asyncio
from collections.abc import Sequence

import pytest

from bleconnect.adapters.linux.rfcomm import (
    RfcommDeviceLink,
    _make_profile,
)
from bleconnect.adapters.linux.trusted_devices import is_trusted
from bleconnect.application.ports import TrustedDevice
from bleconnect.protocol import Packet, encode_packet, read_packet


def test_rfcomm_link_round_trip() -> None:
    async def scenario() -> None:
        received: list[Packet] = []

        async def peer(reader, writer) -> None:
            received.append(await read_packet(reader))
            writer.write(encode_packet(Packet("pong", {"ok": True})))
            await writer.drain()
            writer.close()
            await writer.wait_closed()

        server = await asyncio.start_server(peer, "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]
        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        link = RfcommDeviceLink(reader, writer)
        try:
            await link.send(Packet("ping", {"ts": 1}, b"payload"))
            assert await link.receive() == Packet("pong", {"ok": True})
            assert received == [Packet("ping", {"ts": 1}, b"payload")]
        finally:
            await link.close()
            server.close()
            await server.wait_closed()

    asyncio.run(scenario())


def test_is_trusted_matches_case_insensitively() -> None:
    class Repository:
        async def list_trusted(self) -> Sequence[TrustedDevice]:
            return [TrustedDevice("AA:BB:CC:DD:EE:FF", "Phone")]

        async def save_trusted(self, device) -> None:
            pass

        async def remove_trusted(self, address) -> None:
            pass

    async def scenario() -> None:
        assert await is_trusted(Repository(), "aa:bb:cc:dd:ee:ff") is True
        assert await is_trusted(Repository(), "11:22:33:44:55:66") is False

    asyncio.run(scenario())


def test_profile_exports_expected_bluez_callbacks() -> None:
    pytest.importorskip("dbus_next")

    class DummyServer:
        def _released(self):
            pass

        def _accept_fd(self, _device, _fd):
            pass

        def _drop_link(self, _device):
            pass

    profile = _make_profile(DummyServer())
    methods = {
        method.name: (
            method.in_signature_tree.signature,
            method.out_signature_tree.signature,
        )
        for method in profile._get_methods(profile)
    }
    assert methods == {
        "Release": ("", ""),
        "NewConnection": ("oha{sv}", ""),
        "RequestDisconnection": ("o", ""),
    }
