"""Android BLE peripheral link over a thin native bridge."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Protocol

from ...ble_protocol import (
    DEFAULT_MTU,
    MessageAssembler,
    decode_frame,
    encode_frame,
    encode_packet_chunks,
)
from ...messages import CLIPBOARD, CONTROL_TYPES
from ...protocol import Packet, ProtocolError


class BlePeripheralTransport(Protocol):
    @property
    def mtu_size(self) -> int:
        """Current ATT MTU, or the BLE minimum when unknown."""

    @property
    def is_connected(self) -> bool:
        """Whether a GATT central is currently connected."""

    async def start(self) -> None:
        """Start advertising and the GATT server."""

    async def stop(self) -> None:
        """Stop advertising and close the GATT server."""

    async def send_control(self, data: bytes) -> None:
        """Send raw bytes on the control characteristic."""

    async def send_clipboard(self, data: bytes) -> None:
        """Send raw bytes on the clipboard characteristic."""

    def set_write_handler(
        self, handler: Callable[[str, bytes], None]
    ) -> None:
        """Register a handler for raw control/clipboard writes."""

    def set_connection_handler(self, handler: Callable[[bool], None]) -> None:
        """Register a handler for central connect/disconnect events."""

    def set_mtu_handler(self, handler: Callable[[int], None]) -> None:
        """Register a handler for MTU changes."""


class BlePeripheralLink:
    """PacketLink over the Android BLE peripheral characteristics."""

    def __init__(self, transport: BlePeripheralTransport) -> None:
        self._transport = transport
        self._mtu = DEFAULT_MTU
        self._connected = False
        self._assembler = MessageAssembler()
        self._incoming: asyncio.Queue[Packet | None] = asyncio.Queue()
        self._message_id = 0
        self._closed = False
        transport.set_write_handler(self._on_write)
        transport.set_connection_handler(self._on_connection)
        transport.set_mtu_handler(self._on_mtu)

    @property
    def mtu_size(self) -> int:
        return self._mtu

    @property
    def connected(self) -> bool:
        return self._connected

    async def connect(self) -> None:
        await self._transport.start()
        self._mtu = max(DEFAULT_MTU, self._transport.mtu_size)

    async def send(self, packet: Packet) -> None:
        if self._closed:
            raise ConnectionError("BLE link is closed")
        if not self._connected:
            raise ConnectionError("no BLE central is connected")
        if packet.type == CLIPBOARD:
            send = self._transport.send_clipboard
        elif packet.type in CONTROL_TYPES:
            send = self._transport.send_control
        else:
            raise ProtocolError("BLE link only carries control and clipboard packets")

        for frame in encode_packet_chunks(
            packet, self._next_message_id(), self._mtu
        ):
            await send(encode_frame(frame))

    async def receive(self) -> Packet:
        if self._closed and self._incoming.empty():
            raise ConnectionError("BLE link is closed")
        packet = await self._incoming.get()
        if packet is None:
            raise ConnectionError("BLE link disconnected")
        return packet

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            await self._transport.stop()
        finally:
            self._incoming.put_nowait(None)

    def _next_message_id(self) -> int:
        message_id = self._message_id
        self._message_id = (self._message_id + 1) & 0xFFFFFFFF
        return message_id

    def _on_write(self, _kind: str, data: bytes) -> None:
        try:
            packet = self._assembler.add(decode_frame(data))
        except ProtocolError:
            return
        if packet is not None:
            self._incoming.put_nowait(packet)

    def _on_connection(self, connected: bool) -> None:
        self._connected = connected
        self._assembler.reset()

    def _on_mtu(self, mtu: int) -> None:
        self._mtu = max(DEFAULT_MTU, mtu)


def create_pyjnius_transport(context, log=None) -> BlePeripheralTransport:
    """Create the Android bridge transport; imported only on Android."""
    from .ble_peripheral_pyjnius import PyjniusBlePeripheralTransport

    return PyjniusBlePeripheralTransport(context, log=log)
