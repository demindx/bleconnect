"""UI-agnostic view models shared by Qt and Kivy."""

from __future__ import annotations

from collections.abc import Callable

from ..application.file_transfer_service import TransferProgress
from ..application.ports import FileSource
from ..application.session import ConnectionState
from .app_controller import AppController, AppState

StateListener = Callable[[AppState], None]


class AppViewModel:
    """Expose controller state and commands without any GUI imports."""

    def __init__(self, controller: AppController) -> None:
        self._controller = controller
        self._state = controller.state
        self._listeners: list[StateListener] = []
        self._unsubscribe = controller.subscribe(self._on_state)

    @property
    def state(self) -> AppState:
        return self._state

    @property
    def connection(self) -> ConnectionState:
        return self._state.connection

    @property
    def clipboard_paused(self) -> bool:
        return self._state.clipboard_paused

    @property
    def transfer(self) -> TransferProgress | None:
        return self._state.transfer

    @property
    def last_error(self) -> str | None:
        return self._state.last_error

    def subscribe(self, listener: StateListener) -> Callable[[], None]:
        self._listeners.append(listener)

        def unsubscribe() -> None:
            if listener in self._listeners:
                self._listeners.remove(listener)

        return unsubscribe

    async def start(self) -> None:
        await self._controller.start()

    async def stop(self) -> None:
        await self._controller.stop()

    def pause_clipboard(self) -> None:
        self._controller.pause_clipboard()

    def resume_clipboard(self) -> None:
        self._controller.resume_clipboard()

    async def send_clipboard(self) -> bool:
        return await self._controller.send_clipboard()

    async def send_file(self, source: FileSource) -> TransferProgress:
        return await self._controller.send_file(source)

    async def find_phone(
        self, duration_s: float = 30.0, volume: float = 1.0
    ) -> None:
        await self._controller.find_phone(duration_s, volume)

    def dispose(self) -> None:
        self._unsubscribe()
        self._listeners.clear()

    def _on_state(self, state: AppState) -> None:
        self._state = state
        for listener in tuple(self._listeners):
            listener(state)
