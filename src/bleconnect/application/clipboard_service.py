"""Clipboard synchronization behavior shared by both platforms."""

from __future__ import annotations

import asyncio

from ..messages import CLIPBOARD, clipboard_packet
from ..protocol import Packet
from .ports import ClipboardPort, ClipboardSnapshot, ClipboardWatcher, PacketLink

MAX_CLIPBOARD_BYTES = 64 * 1024


class ClipboardService:
    """Send changed text and apply peer updates without echoing them back."""

    def __init__(
        self,
        clipboard: ClipboardPort,
        link: PacketLink,
        *,
        max_bytes: int = MAX_CLIPBOARD_BYTES,
    ) -> None:
        if max_bytes <= 0:
            raise ValueError("max_bytes must be positive")
        self._clipboard = clipboard
        self._link = link
        self._max_bytes = max_bytes
        self._paused = False
        self._last_sent: str | None = None
        self._last_received: str | None = None

    @property
    def paused(self) -> bool:
        return self._paused

    def pause(self) -> None:
        self._paused = True

    def resume(self) -> None:
        self._paused = False

    async def publish_current(self, *, force: bool = False) -> bool:
        """Read and send the current clipboard when eligible."""
        return await self.publish_snapshot(
            await self._clipboard.read_text(), force=force
        )

    async def publish_snapshot(
        self, snapshot: ClipboardSnapshot | None, *, force: bool = False
    ) -> bool:
        """Send one clipboard snapshot when it is new and safe.

        ``force`` is used by the explicit UI button: it bypasses echo
        suppression so the user can resend the last received text.
        """
        if self._paused or snapshot is None:
            return False

        text = snapshot.text
        if snapshot.sensitive or not text:
            return False
        if len(text.encode("utf-8")) > self._max_bytes:
            return False
        if not force:
            if text == self._last_received:
                self._last_received = None
                return False
            if text == self._last_sent:
                return False

        await self._link.send(clipboard_packet(text))
        self._last_sent = text
        self._last_received = None
        return True

    async def handle_packet(self, packet: Packet) -> bool:
        """Apply an incoming clipboard packet once."""
        if self._paused or packet.type != CLIPBOARD:
            return False

        if packet.body.get("sensitive") is True:
            return False
        text = packet.body.get("text")
        if not isinstance(text, str) or not text:
            return False
        if len(text.encode("utf-8")) > self._max_bytes:
            return False
        if text == self._last_received or text == self._last_sent:
            return False

        current = await self._clipboard.read_text()
        if current is not None and current.text == text:
            self._last_received = text
            return False

        await self._clipboard.write_text(text)
        self._last_received = text
        return True

    async def run(
        self, watcher: ClipboardWatcher, stop_event: asyncio.Event
    ) -> None:
        """Publish clipboard changes until stopped."""
        async for snapshot in watcher.changes():
            if stop_event.is_set():
                return
            await self.publish_snapshot(snapshot)
