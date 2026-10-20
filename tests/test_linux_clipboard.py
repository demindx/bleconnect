import asyncio

import pytest

from bleconnect.adapters.linux.clipboard import (
    ClipboardUnavailableError,
    CommandClipboard,
    PollingClipboardWatcher,
    WaylandClipboardProvider,
    XclipClipboardProvider,
    resolve_linux_clipboard,
)
from bleconnect.application.ports import ClipboardPort, ClipboardSnapshot


def test_command_clipboard_reads_text() -> None:
    async def runner(command, input_bytes):
        assert command[0] == "paste"
        return 0, b"hello", b""

    async def scenario() -> None:
        clipboard = CommandClipboard(("paste",), ("copy",), command_runner=runner)
        assert await clipboard.read_text() == ClipboardSnapshot("hello")

    asyncio.run(scenario())


def test_command_clipboard_marks_kde_password_manager_clip() -> None:
    calls: list[tuple[str, ...]] = []

    async def runner(command, input_bytes):
        calls.append(tuple(command))
        return 0, b"x-kde-passwordManagerHint", b""

    async def scenario() -> None:
        clipboard = CommandClipboard(
            ("paste",),
            ("copy",),
            types_command=("paste", "--list-types"),
            command_runner=runner,
        )
        assert await clipboard.read_text() == ClipboardSnapshot("", sensitive=True)

    asyncio.run(scenario())
    assert calls == [("paste", "--list-types")]


def test_command_clipboard_writes_text() -> None:
    received: list[bytes | None] = []

    async def runner(command, input_bytes):
        received.append(input_bytes)
        return 0, b"", b""

    async def scenario() -> None:
        clipboard = CommandClipboard(("paste",), ("copy",), command_runner=runner)
        await clipboard.write_text("hello")
        with pytest.raises(ClipboardUnavailableError):
            await CommandClipboard(
                ("paste",),
                ("copy",),
                command_runner=lambda command, data: _failing_runner(command, data),
            ).write_text("hello")

    asyncio.run(scenario())
    assert received == [b"hello"]


async def _failing_runner(command, input_bytes):
    return 1, b"", b"denied"


def test_resolve_clipboard_uses_first_available_provider() -> None:
    class Provider:
        def __init__(self, result: ClipboardPort | None) -> None:
            self._result = result

        def create(self, env):
            return self._result

    async def runner(command, input_bytes):
        return 0, b"", b""

    clipboard = CommandClipboard(("paste",), ("copy",), command_runner=runner)
    assert resolve_linux_clipboard([Provider(None), Provider(clipboard)], {}) is clipboard


def test_resolve_clipboard_rejects_session_without_display() -> None:
    class Provider:
        def create(self, env):
            return None

    with pytest.raises(ClipboardUnavailableError):
        resolve_linux_clipboard([Provider()], {})


def test_wayland_provider_requires_tools(monkeypatch) -> None:
    def fake_which(name: str) -> str | None:
        return "/usr/bin/" + name if name in {"wl-copy", "wl-paste"} else None

    monkeypatch.setattr("shutil.which", fake_which)

    async def runner(command, input_bytes):
        return 0, b"", b""

    provider = WaylandClipboardProvider(command_runner=runner)
    assert provider.create({"WAYLAND_DISPLAY": "wayland-0"}) is not None
    assert provider.create({}) is None


def test_xclip_provider_requires_tools(monkeypatch) -> None:
    monkeypatch.setattr(
        "shutil.which", lambda name: "/usr/bin/xclip" if name == "xclip" else None
    )

    async def runner(command, input_bytes):
        return 0, b"", b""

    provider = XclipClipboardProvider(command_runner=runner)
    assert provider.create({"DISPLAY": ":0"}) is not None
    assert provider.create({}) is None


def test_polling_watcher_yields_changes() -> None:
    class MutableClipboard:
        def __init__(self) -> None:
            self.snapshot = ClipboardSnapshot("one")

        async def read_text(self):
            return self.snapshot

        async def write_text(self, text: str) -> None:
            self.snapshot = ClipboardSnapshot(text)

    async def scenario() -> None:
        clipboard = MutableClipboard()
        watcher = PollingClipboardWatcher(clipboard, interval=0.01)
        changes = watcher.changes()
        assert await asyncio.wait_for(anext(changes), 1) == ClipboardSnapshot("one")
        clipboard.snapshot = ClipboardSnapshot("two")
        assert await asyncio.wait_for(anext(changes), 1) == ClipboardSnapshot("two")
        await changes.aclose()

    asyncio.run(scenario())
