import asyncio

from bleconnect.application.clipboard_service import ClipboardSyncService
from bleconnect.application.ports import ClipboardSnapshot


class MemoryClipboard:
    def __init__(self, text: str | None = None, sensitive: bool = False) -> None:
        self.snapshot = ClipboardSnapshot(text, sensitive) if text is not None else None
        self.writes: list[str] = []

    async def read_text(self) -> ClipboardSnapshot | None:
        return self.snapshot

    async def write_text(self, text: str) -> None:
        self.snapshot = ClipboardSnapshot(text)
        self.writes.append(text)


class MemoryLink:
    def __init__(self) -> None:
        self.sent: list[dict[str, object]] = []

    async def send(self, message: dict[str, object]) -> None:
        self.sent.append(message)


class ReceivingMemoryLink(MemoryLink):
    def __init__(self) -> None:
        super().__init__()
        self.incoming: asyncio.Queue[dict[str, object]] = asyncio.Queue()

    async def receive(self) -> dict[str, object]:
        return await self.incoming.get()


def test_clipboard_sends_new_text_once_and_skips_sensitive_text() -> None:
    clipboard = MemoryClipboard("secret", sensitive=True)
    link = MemoryLink()
    service = ClipboardSyncService(clipboard, link)

    async def scenario() -> None:
        assert not await service.publish_current()
        clipboard.snapshot = ClipboardSnapshot("hello")
        assert await service.publish_current()
        assert not await service.publish_current()

    asyncio.run(scenario())
    assert len(link.sent) == 1
    assert link.sent[0]["body"] == {"text": "hello"}


def test_received_clipboard_is_not_echoed_back() -> None:
    clipboard = MemoryClipboard("local")
    link = MemoryLink()
    service = ClipboardSyncService(clipboard, link)
    incoming = {"type": "clipboard", "body": {"text": "from peer"}}

    async def scenario() -> None:
        assert await service.handle_packet(incoming)
        assert not await service.publish_current()

    asyncio.run(scenario())
    assert clipboard.writes == ["from peer"]
    assert link.sent == []


def test_text_changed_locally_after_peer_update_can_be_sent_later() -> None:
    clipboard = MemoryClipboard("local")
    link = MemoryLink()
    service = ClipboardSyncService(clipboard, link)

    async def scenario() -> None:
        await service.handle_packet({"type": "clipboard", "body": {"text": "peer"}})
        assert not await service.publish_current()
        clipboard.snapshot = ClipboardSnapshot("another local value")
        assert await service.publish_current()
        clipboard.snapshot = ClipboardSnapshot("peer")
        assert await service.publish_current()

    asyncio.run(scenario())
    assert [message["body"] for message in link.sent] == [
        {"text": "another local value"},
        {"text": "peer"},
    ]


def test_run_polls_local_clipboard_and_stops_after_peer_update() -> None:
    stopped = asyncio.Event()

    class StoppingClipboard(MemoryClipboard):
        async def write_text(self, text: str) -> None:
            await super().write_text(text)
            stopped.set()

    clipboard = StoppingClipboard("desktop text")
    link = ReceivingMemoryLink()
    service = ClipboardSyncService(clipboard, link)
    link.incoming.put_nowait({"type": "clipboard", "body": {"text": "phone text"}})

    asyncio.run(service.run(stopped, poll_interval=0.01))
    assert link.sent == [
        {"version": 1, "type": "clipboard", "body": {"text": "desktop text"}}
    ]
    assert clipboard.writes == ["phone text"]
