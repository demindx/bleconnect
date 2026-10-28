"""Application facade shared by the Qt and Kivy interfaces."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, replace

from ..application.clipboard_service import ClipboardService
from ..application.file_transfer_service import (
    FileTransferService,
    TransferError,
    TransferProgress,
)
from ..application.pairing_service import PairingService
from ..application.ports import ClipboardWatcher, FileSource, PacketLink
from ..application.session import ConnectionState
from ..messages import FIND_PHONE, control_packet

AppListener = Callable[["AppState"], None]


@dataclass(frozen=True)
class AppState:
    connection: ConnectionState = ConnectionState.STOPPED
    clipboard_paused: bool = False
    transfer: TransferProgress | None = None
    last_error: str | None = None
    peer_name: str | None = None


class AppController:
    """One entry point for connection, clipboard, files, and settings."""

    def __init__(
        self,
        control_link: PacketLink,
        clipboard: ClipboardService,
        *,
        files: FileTransferService | None = None,
        pairing: PairingService | None = None,
        watcher: ClipboardWatcher | None = None,
    ) -> None:
        self._control_link = control_link
        self._clipboard = clipboard
        self._files = files
        self._pairing = pairing
        self._watcher = watcher
        self._state = AppState(clipboard_paused=clipboard.paused)
        self._listeners: list[AppListener] = []
        self._stop_event: asyncio.Event | None = None
        self._watcher_task: asyncio.Task[None] | None = None
        if files is not None:
            files.set_progress_listener(self._on_transfer_progress)

    @property
    def state(self) -> AppState:
        return self._state

    def subscribe(self, listener: AppListener) -> Callable[[], None]:
        self._listeners.append(listener)

        def unsubscribe() -> None:
            if listener in self._listeners:
                self._listeners.remove(listener)

        return unsubscribe

    async def start(self) -> None:
        if self._watcher is None or self._watcher_task is not None:
            return
        self._stop_event = asyncio.Event()
        self._watcher_task = asyncio.create_task(
            self._clipboard.run(self._watcher, self._stop_event)
        )

    async def stop(self) -> None:
        if self._stop_event is not None:
            self._stop_event.set()
        if self._watcher_task is not None:
            self._watcher_task.cancel()
            await asyncio.gather(self._watcher_task, return_exceptions=True)
            self._watcher_task = None
        if self._files is not None:
            await self._files.close()
        await self._control_link.close()
        self._set_state(connection=ConnectionState.STOPPED)

    def set_connection_state(
        self, state: ConnectionState, *, peer_name: str | None = None
    ) -> None:
        self._set_state(connection=state, peer_name=peer_name)

    def pause_clipboard(self) -> None:
        self._clipboard.pause()
        self._set_state(clipboard_paused=True)

    def resume_clipboard(self) -> None:
        self._clipboard.resume()
        self._set_state(clipboard_paused=False)

    async def send_clipboard(self) -> bool:
        try:
            return await self._clipboard.publish_current(force=True)
        except Exception as exc:
            self._set_state(last_error=str(exc))
            raise

    async def send_file(self, source: FileSource) -> TransferProgress:
        if self._files is None:
            raise RuntimeError("file transfer is not configured")
        try:
            return await self._files.send(source)
        except TransferError as exc:
            self._set_state(last_error=exc.code)
            raise

    async def find_phone(
        self, duration_s: float = 30.0, volume: float = 1.0
    ) -> None:
        if duration_s <= 0:
            raise ValueError("duration must be positive")
        if not 0.0 <= volume <= 1.0:
            raise ValueError("volume must be between 0 and 1")
        await self._control_link.send(
            control_packet(
                FIND_PHONE, {"duration_s": duration_s, "volume": volume}
            )
        )

    async def forget_device(self, address: str) -> None:
        if self._pairing is None:
            raise RuntimeError("pairing is not configured")
        await self._pairing.forget(address)

    def _on_transfer_progress(self, progress: TransferProgress) -> None:
        self._set_state(transfer=progress)

    def _set_state(self, **changes: object) -> None:
        self._state = replace(self._state, **changes)
        for listener in tuple(self._listeners):
            listener(self._state)
