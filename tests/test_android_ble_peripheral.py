import asyncio

import pytest

from bleconnect.adapters.android.ble_peripheral import BlePeripheralLink
from bleconnect.ble_protocol import (
    MessageAssembler,
    decode_frame,
    encode_frame,
    encode_packet_chunks,
)
from bleconnect.messages import PING, control_packet
from bleconnect.protocol import Packet, ProtocolError


class FakePeripheralTransport:
    def __init__(self, mtu: int = 23) -> None:
        self._mtu = mtu
        self.connected = False
        self.started = False
        self.control_writes: list[bytes] = []
        self.clipboard_writes: list[bytes] = []
        self.write_handler = None
        self.connection_handler = None
        self.mtu_handler = None

    @property
    def mtu_size(self) -> int:
        return self._mtu

    @property
    def is_connected(self) -> bool:
        return self.connected

    async def start(self) -> None:
        self.started = True

    async def stop(self) -> None:
        self.started = False

    async def send_control(self, data: bytes) -> None:
        self.control_writes.append(data)

    async def send_clipboard(self, data: bytes) -> None:
        self.clipboard_writes.append(data)

    def set_write_handler(self, handler) -> None:
        self.write_handler = handler

    def set_connection_handler(self, handler) -> None:
        self.connection_handler = handler

    def set_mtu_handler(self, handler) -> None:
        self.mtu_handler = handler


def _assemble(frames: list[bytes]) -> Packet:
    assembler = MessageAssembler()
    results = [assembler.add(decode_frame(data)) for data in frames]
    return results[-1]


def test_connect_starts_transport_and_requires_a_central_for_send() -> None:
    async def scenario() -> None:
        transport = FakePeripheralTransport()
        link = BlePeripheralLink(transport)
        await link.connect()
        assert transport.started is True

        with pytest.raises(ConnectionError):
            await link.send(control_packet(PING))

        transport.connected = True
        transport.connection_handler(True)
        await link.send(control_packet(PING))
        assert transport.control_writes

    asyncio.run(scenario())


def test_send_control_packet_is_chunked() -> None:
    async def scenario() -> None:
        transport = FakePeripheralTransport(mtu=23)
        link = BlePeripheralLink(transport)
        await link.connect()
        transport.connection_handler(True)
        packet = control_packet(PING, {"ts": 1})

        await link.send(packet)

        assert _assemble(transport.control_writes) == packet

    asyncio.run(scenario())


def test_send_clipboard_packet_uses_clipboard_chunks() -> None:
    async def scenario() -> None:
        transport = FakePeripheralTransport(mtu=23)
        link = BlePeripheralLink(transport)
        await link.connect()
        transport.connection_handler(True)
        packet = Packet("clipboard", {"text": "hello" * 20})

        await link.send(packet)

        assert not transport.control_writes
        assert _assemble(transport.clipboard_writes) == packet

    asyncio.run(scenario())


def test_receive_reassembles_writes() -> None:
    async def scenario() -> None:
        transport = FakePeripheralTransport(mtu=23)
        link = BlePeripheralLink(transport)
        await link.connect()
        packet = Packet("clipboard", {"text": "abcdefghijklmno"})

        for frame in encode_packet_chunks(packet, 4, 23):
            transport.write_handler("clipboard", encode_frame(frame))

        assert await asyncio.wait_for(link.receive(), 1) == packet

    asyncio.run(scenario())


def test_mtu_handler_updates_chunking_size() -> None:
    async def scenario() -> None:
        transport = FakePeripheralTransport()
        link = BlePeripheralLink(transport)
        await link.connect()
        transport.mtu_handler(517)
        assert link.mtu_size == 517

    asyncio.run(scenario())


def test_close_stops_transport_and_rejects_sends() -> None:
    async def scenario() -> None:
        transport = FakePeripheralTransport()
        link = BlePeripheralLink(transport)
        await link.connect()
        await link.close()
        assert transport.started is False
        with pytest.raises(ConnectionError):
            await link.send(control_packet(PING))

    asyncio.run(scenario())


def test_unsupported_packet_is_rejected() -> None:
    async def scenario() -> None:
        transport = FakePeripheralTransport()
        link = BlePeripheralLink(transport)
        await link.connect()
        transport.connection_handler(True)
        with pytest.raises(ProtocolError):
            await link.send(Packet("file_offer", {}))

    asyncio.run(scenario())


def test_reconnect_resets_message_dedupe_state() -> None:
    async def scenario() -> None:
        transport = FakePeripheralTransport(mtu=23)
        link = BlePeripheralLink(transport)
        await link.connect()
        packet = Packet("clipboard", {"text": "abcdefghijklmno"})

        transport.connection_handler(True)
        for frame in encode_packet_chunks(packet, 5, 23):
            transport.write_handler("clipboard", encode_frame(frame))
        assert await asyncio.wait_for(link.receive(), 1) == packet

        transport.connection_handler(False)
        transport.connection_handler(True)
        for frame in encode_packet_chunks(packet, 5, 23):
            transport.write_handler("clipboard", encode_frame(frame))
        assert await asyncio.wait_for(link.receive(), 1) == packet

    asyncio.run(scenario())
