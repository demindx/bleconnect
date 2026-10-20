import asyncio

import pytest

from bleconnect.adapters.linux.ble_central import BleCentralLink
from bleconnect.ble_protocol import (
    BLE_CLIPBOARD_CHARACTERISTIC_UUID,
    BLE_CONTROL_CHARACTERISTIC_UUID,
    MessageAssembler,
    decode_frame,
    encode_frame,
    encode_packet_chunks,
)
from bleconnect.messages import FIND_PHONE, control_packet
from bleconnect.protocol import Packet, ProtocolError


class FakeTransport:
    def __init__(self, mtu: int = 23) -> None:
        self._mtu = mtu
        self.connected = False
        self.writes: list[tuple[str, bytes]] = []
        self.notify: dict[str, callable] = {}
        self.disconnect_handler = None

    @property
    def mtu_size(self) -> int:
        return self._mtu

    async def connect(self) -> None:
        self.connected = True

    async def disconnect(self) -> None:
        self.connected = False

    async def write(self, characteristic: str, data: bytes) -> None:
        self.writes.append((characteristic, data))

    async def start_notify(self, characteristic, callback) -> None:
        self.notify[characteristic] = callback

    def set_disconnect_handler(self, handler) -> None:
        self.disconnect_handler = handler


def _assemble(writes: list[tuple[str, bytes]]) -> Packet:
    assembler = MessageAssembler()
    results = [assembler.add(decode_frame(data)) for _, data in writes]
    return results[-1]


def test_connect_subscribes_to_both_characteristics() -> None:
    async def scenario() -> None:
        transport = FakeTransport(mtu=517)
        link = BleCentralLink(transport)
        await link.connect()

        assert transport.connected is True
        assert link.mtu_size == 517
        assert set(transport.notify) == {
            BLE_CONTROL_CHARACTERISTIC_UUID,
            BLE_CLIPBOARD_CHARACTERISTIC_UUID,
        }

    asyncio.run(scenario())


def test_send_control_packet_is_chunked_on_control_characteristic() -> None:
    async def scenario() -> None:
        transport = FakeTransport(mtu=23)
        link = BleCentralLink(transport)
        await link.connect()
        packet = control_packet(FIND_PHONE, {"duration_s": 30, "volume": 1.0})

        await link.send(packet)

        assert transport.writes
        assert all(
            characteristic == BLE_CONTROL_CHARACTERISTIC_UUID
            for characteristic, _ in transport.writes
        )
        assert _assemble(transport.writes) == packet

    asyncio.run(scenario())


def test_send_clipboard_packet_uses_clipboard_characteristic() -> None:
    async def scenario() -> None:
        transport = FakeTransport(mtu=23)
        link = BleCentralLink(transport)
        await link.connect()
        packet = Packet("clipboard", {"text": "hello" * 20})

        await link.send(packet)

        assert all(
            characteristic == BLE_CLIPBOARD_CHARACTERISTIC_UUID
            for characteristic, _ in transport.writes
        )
        assert _assemble(transport.writes) == packet

    asyncio.run(scenario())


def test_receive_reassembles_frames_from_notifications() -> None:
    async def scenario() -> None:
        transport = FakeTransport(mtu=23)
        link = BleCentralLink(transport)
        await link.connect()
        packet = Packet("clipboard", {"text": "abcdefghijklmno"})
        frames = encode_packet_chunks(packet, 9, 23)
        callback = transport.notify[BLE_CLIPBOARD_CHARACTERISTIC_UUID]

        for frame in frames:
            callback(encode_frame(frame))

        assert await asyncio.wait_for(link.receive(), 1) == packet

    asyncio.run(scenario())


def test_disconnect_unblocks_receive() -> None:
    async def scenario() -> None:
        transport = FakeTransport()
        link = BleCentralLink(transport)
        await link.connect()

        transport.disconnect_handler()

        with pytest.raises(ConnectionError):
            await asyncio.wait_for(link.receive(), 1)

    asyncio.run(scenario())


def test_unsupported_packet_is_rejected() -> None:
    async def scenario() -> None:
        link = BleCentralLink(FakeTransport())
        await link.connect()
        with pytest.raises(ProtocolError):
            await link.send(Packet("file_offer", {}))

    asyncio.run(scenario())


def test_close_rejects_later_sends() -> None:
    async def scenario() -> None:
        link = BleCentralLink(FakeTransport())
        await link.connect()
        await link.close()
        with pytest.raises(ConnectionError):
            await link.send(control_packet(FIND_PHONE))

    asyncio.run(scenario())
