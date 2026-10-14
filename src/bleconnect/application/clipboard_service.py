"""Clipboard synchronization behavior shared by platform adapters."""

from __future__ import annotations

import asyncio

from .ports import ClipboardPort, DeviceLink
from ..protocol import packet


class ClipboardSyncService:
    """Send changed text and apply peer updates without echoing them back."""

    def __init__(self, clipboard: ClipboardPort, link: DeviceLink) -> None:
        self._clipboard = clipboard
        self._link = link
        self._last_sent: str | None = None
        self._last_received: str | None = None

    async def run(
        self, stop_event: asyncio.Event, poll_interval: float = 0.5
    ) -> None:
        """Poll local text and receive peer updates until stopped or disconnected."""
        if poll_interval <= 0:
            raise ValueError("poll_interval must be positive")

        async def poll_clipboard() -> None:
            while not stop_event.is_set():
                await self.publish_current()
                try:
                    await asyncio.wait_for(stop_event.wait(), timeout=poll_interval)
                except TimeoutError:
                    pass

        async def receive_packets() -> None:
            while not stop_event.is_set():
                await self.handle_packet(await self._link.receive())

        poll_task = asyncio.create_task(poll_clipboard())
        receive_task = asyncio.create_task(receive_packets())
        stop_task = asyncio.create_task(stop_event.wait())
        tasks = (poll_task, receive_task, stop_task)
        try:
            done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                if task is not stop_task:
                    await task
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

    async def publish_current(self) -> bool:
        """Send current clipboard text when it is new and not marked sensitive."""
        snapshot = await self._clipboard.read_text()
        if snapshot is None or snapshot.sensitive or not snapshot.text:
            return False
        if snapshot.text == self._last_received:
            self._last_received = None
            return False
        if snapshot.text == self._last_sent:
            return False
        await self._link.send(packet("clipboard", {"text": snapshot.text}))
        self._last_sent = snapshot.text
        self._last_received = None
        return True

    async def handle_packet(self, message: dict[str, object]) -> bool:
        """Apply an incoming clipboard packet and remember it to prevent echo."""
        if message.get("type") != "clipboard":
            return False
        body = message.get("body")
        if not isinstance(body, dict):
            return False
        text = body.get("text")
        if not isinstance(text, str) or not text or text == self._last_received:
            return False
        current = await self._clipboard.read_text()
        if current is not None and current.text == text:
            self._last_received = text
            return False
        await self._clipboard.write_text(text)
        self._last_received = text
        return True
