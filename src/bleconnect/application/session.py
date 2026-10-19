"""Packet dispatch and one-session receive loop."""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Awaitable, Callable
from enum import Enum

from ..protocol import Packet
from .ports import PacketLink

PacketHandler = Callable[[Packet], Awaitable[None] | None]


class ConnectionState(Enum):
    STOPPED = "stopped"
    SCANNING = "scanning"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    BACKOFF = "backoff"
    ERROR = "error"


class PacketDispatcher:
    """Route packets by type without coupling services to a transport."""

    def __init__(self) -> None:
        self._handlers: dict[str, PacketHandler] = {}

    def register(self, packet_type: str, handler: PacketHandler) -> None:
        if not packet_type:
            raise ValueError("packet type must not be empty")
        if packet_type in self._handlers:
            raise ValueError(f"handler already registered for {packet_type}")
        self._handlers[packet_type] = handler

    def unregister(self, packet_type: str) -> None:
        self._handlers.pop(packet_type, None)

    async def dispatch(self, packet: Packet) -> bool:
        handler = self._handlers.get(packet.type)
        if handler is None:
            return False
        result = handler(packet)
        if inspect.isawaitable(result):
            await result
        return True


class Session:
    """Receive packets from one link and dispatch them until stopped."""

    def __init__(self, link: PacketLink, dispatcher: PacketDispatcher) -> None:
        self._link = link
        self._dispatcher = dispatcher

    async def send(self, packet: Packet) -> None:
        await self._link.send(packet)

    async def run(self, stop_event: asyncio.Event) -> None:
        while not stop_event.is_set():
            receive_task = asyncio.create_task(self._link.receive())
            stop_task = asyncio.create_task(stop_event.wait())
            done, pending = await asyncio.wait(
                {receive_task, stop_task}, return_when=asyncio.FIRST_COMPLETED
            )
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)

            if stop_task in done:
                return

            await self._dispatcher.dispatch(receive_task.result())

    async def close(self) -> None:
        await self._link.close()
