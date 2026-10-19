import asyncio

from bleconnect.application.clipboard_service import (
    MAX_CLIPBOARD_BYTES,
    ClipboardService,
)
from bleconnect.application.ports import ClipboardSnapshot
from bleconnect.protocol import Packet
from tests.support import MemoryClipboard, paired_links


def test_publish_new_text_once() -> None:
    async def scenario() -> None:
        clipboard = MemoryClipboard("hello")
        link, peer = paired_links()
        service = ClipboardService(clipboard, link)

        assert await service.publish_current() is True
        assert await service.publish_current() is False
        assert await asyncio.wait_for(peer.incoming.get(), 1) == Packet(
            "clipboard", {"text": "hello"}
        )

    asyncio.run(scenario())


def test_sensitive_and_oversized_text_is_skipped() -> None:
    async def scenario() -> None:
        clipboard = MemoryClipboard("secret", sensitive=True)
        link, peer = paired_links()
        service = ClipboardService(clipboard, link)

        assert await service.publish_current() is False
        clipboard.snapshot = ClipboardSnapshot("x" * (MAX_CLIPBOARD_BYTES + 1))
        assert await service.publish_current() is False
        assert peer.incoming.empty()

    asyncio.run(scenario())


def test_incoming_text_is_applied_without_echo() -> None:
    async def scenario() -> None:
        clipboard = MemoryClipboard("local")
        link, peer = paired_links()
        service = ClipboardService(clipboard, link)

        assert await service.handle_packet(
            Packet("clipboard", {"text": "remote"})
        )
        assert clipboard.writes == ["remote"]
        assert await service.publish_current() is False
        assert peer.incoming.empty()

    asyncio.run(scenario())


def test_pause_blocks_sending_and_applying() -> None:
    async def scenario() -> None:
        clipboard = MemoryClipboard("local")
        link, peer = paired_links()
        service = ClipboardService(clipboard, link)

        service.pause()
        assert await service.publish_current() is False
        assert await service.handle_packet(
            Packet("clipboard", {"text": "remote"})
        ) is False
        assert clipboard.writes == []

        service.resume()
        assert await service.publish_current() is True

    asyncio.run(scenario())
