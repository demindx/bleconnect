"""Async RFCOMM packet link for Linux Bluetooth sockets."""

from __future__ import annotations

import asyncio
import socket
from typing import Any

from ...protocol import encode_packet, read_packet


class RfcommDeviceLink:
    """DeviceLink implementation over an already connected RFCOMM socket.

    Pairing and service discovery are platform responsibilities. Construct the
    link only after BlueZ has supplied a connected RFCOMM socket.
    """

    def __init__(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        self._reader = reader
        self._writer = writer
        self._send_lock = asyncio.Lock()
        self._closed = False

    @classmethod
    async def connect(cls, address: str, channel: int) -> RfcommDeviceLink:
        """Connect to a paired peer by Bluetooth address and RFCOMM channel."""
        if not hasattr(socket, "AF_BLUETOOTH") or not hasattr(socket, "BTPROTO_RFCOMM"):
            raise OSError("RFCOMM is available only on supported Linux systems")
        if not 1 <= channel <= 30:
            raise ValueError("RFCOMM channel must be between 1 and 30")
        bluetooth_socket = socket.socket(
            socket.AF_BLUETOOTH, socket.SOCK_STREAM, socket.BTPROTO_RFCOMM
        )
        bluetooth_socket.setblocking(False)
        try:
            await asyncio.get_running_loop().sock_connect(
                bluetooth_socket, (address, channel)
            )
            reader, writer = await asyncio.open_connection(sock=bluetooth_socket)
        except BaseException:
            bluetooth_socket.close()
            raise
        return cls(reader, writer)

    async def send(self, packet: dict[str, Any]) -> None:
        if self._closed:
            raise ConnectionError("RFCOMM link is closed")
        frame = encode_packet(packet)
        async with self._send_lock:
            self._writer.write(frame)
            await self._writer.drain()

    async def receive(self) -> dict[str, Any]:
        if self._closed:
            raise ConnectionError("RFCOMM link is closed")
        return await read_packet(self._reader)

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._writer.close()
        try:
            await self._writer.wait_closed()
        except OSError:
            pass
