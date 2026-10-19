"""In-memory test doubles for transport, clipboard, and file behavior."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from bleconnect.application.ports import ClipboardSnapshot, FileSink
from bleconnect.protocol import Packet


class MemoryClipboard:
    def __init__(self, text: str | None = None, sensitive: bool = False) -> None:
        self.snapshot = (
            ClipboardSnapshot(text, sensitive) if text is not None else None
        )
        self.writes: list[str] = []

    async def read_text(self) -> ClipboardSnapshot | None:
        return self.snapshot

    async def write_text(self, text: str) -> None:
        self.snapshot = ClipboardSnapshot(text)
        self.writes.append(text)


class MemoryWatcher:
    def __init__(self) -> None:
        self._queue: asyncio.Queue[ClipboardSnapshot] = asyncio.Queue()

    def push(self, snapshot: ClipboardSnapshot) -> None:
        self._queue.put_nowait(snapshot)

    async def changes(self) -> AsyncIterator[ClipboardSnapshot]:
        while True:
            yield await self._queue.get()


class QueueLink:
    def __init__(self) -> None:
        self.incoming: asyncio.Queue[Packet] = asyncio.Queue()
        self._peer: QueueLink | None = None
        self.closed = False

    def connect(self, peer: QueueLink) -> None:
        self._peer = peer

    async def send(self, packet: Packet) -> None:
        if self.closed:
            raise ConnectionError("link is closed")
        if self._peer is None:
            raise RuntimeError("link is not connected")
        await self._peer.incoming.put(packet)

    async def receive(self) -> Packet:
        if self.closed:
            raise ConnectionError("link is closed")
        return await self.incoming.get()

    async def close(self) -> None:
        self.closed = True


def paired_links() -> tuple[QueueLink, QueueLink]:
    first = QueueLink()
    second = QueueLink()
    first.connect(second)
    second.connect(first)
    return first, second


class MemoryFileSource:
    def __init__(self, name: str, data: bytes) -> None:
        self._name = name
        self.data = data

    @property
    def name(self) -> str:
        return self._name

    @property
    def size(self) -> int:
        return len(self.data)

    async def read_chunks(self, chunk_size: int) -> AsyncIterator[bytes]:
        for index in range(0, len(self.data), chunk_size):
            yield self.data[index : index + chunk_size]


class MemoryFileSink:
    def __init__(self, name: str, size: int) -> None:
        self.name = name
        self.size = size
        self.data = bytearray()
        self.finished = False
        self.aborted = False
        self.sha256: str | None = None

    async def write(self, data: bytes) -> None:
        self.data.extend(data)

    async def finish(self, sha256: str) -> None:
        self.finished = True
        self.sha256 = sha256

    async def abort(self) -> None:
        self.aborted = True
        self.data.clear()


class MemorySinkFactory:
    def __init__(self) -> None:
        self.sinks: list[MemoryFileSink] = []

    async def create(self, name: str, size: int) -> FileSink:
        sink = MemoryFileSink(name, size)
        self.sinks.append(sink)
        return sink


class MutatingLink:
    """Wrap a link and replace the completion hash for negative tests."""

    def __init__(self, inner: QueueLink, replacement: str) -> None:
        self._inner = inner
        self._replacement = replacement

    async def send(self, packet: Packet) -> None:
        if packet.type == "file_complete":
            body = dict(packet.body)
            body["sha256"] = self._replacement
            packet = Packet(packet.type, body)
        await self._inner.send(packet)

    async def receive(self) -> Packet:
        return await self._inner.receive()

    async def close(self) -> None:
        await self._inner.close()
