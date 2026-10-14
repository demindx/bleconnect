import asyncio

import pytest

from bleconnect.adapters.linux.clipboard import (
    ClipboardUnavailableError,
    CommandClipboard,
    WaylandClipboardProvider,
    XclipClipboardProvider,
    resolve_linux_clipboard,
)


def test_provider_resolver_selects_wayland_backend_first(monkeypatch) -> None:
    import bleconnect.adapters.linux.clipboard as adapter

    monkeypatch.setattr(
        adapter.shutil,
        "which",
        lambda name: f"/usr/bin/{name}" if name in {"wl-copy", "wl-paste", "xclip"} else None,
    )
    clipboard = resolve_linux_clipboard(
        [WaylandClipboardProvider(), XclipClipboardProvider()],
        env={"WAYLAND_DISPLAY": "wayland-0", "DISPLAY": ":0"},
    )
    assert isinstance(clipboard, CommandClipboard)
    assert clipboard._read_command == (
        "/usr/bin/wl-paste",
        "--no-newline",
        "--type",
        "text/plain",
    )
    assert clipboard._write_command == (
        "/usr/bin/wl-copy",
        "--type",
        "text/plain;charset=utf-8",
    )
    assert clipboard._types_command == ("/usr/bin/wl-paste", "--list-types")


def test_resolver_uses_next_injected_provider_when_wayland_unavailable(monkeypatch) -> None:
    import bleconnect.adapters.linux.clipboard as adapter

    monkeypatch.setattr(
        adapter.shutil,
        "which",
        lambda name: "/usr/bin/xclip" if name == "xclip" else None,
    )
    clipboard = resolve_linux_clipboard(
        [WaylandClipboardProvider(), XclipClipboardProvider()],
        env={"WAYLAND_DISPLAY": "wayland-0", "DISPLAY": ":0"},
    )
    assert isinstance(clipboard, CommandClipboard)
    assert clipboard._read_command[0] == "/usr/bin/xclip"


def test_wayland_read_and_write_use_utf8_and_sensitive_marker() -> None:
    calls: list[tuple[tuple[str, ...], bytes | None]] = []

    async def runner(command, input_bytes):
        calls.append((tuple(command), input_bytes))
        if tuple(command) == ("wl-types",):
            return 0, b"text/plain", b""
        if input_bytes is None:
            return 0, "zażółć 🌍".encode(), b""
        return 0, b"", b""

    clipboard = CommandClipboard(
        read_command=["wl-paste"],
        write_command=["wl-copy"],
        types_command=["wl-types"],
        command_runner=runner,
        sensitive_detector=lambda text: "secret" in text,
    )

    async def scenario() -> None:
        snapshot = await clipboard.read_text()
        assert snapshot is not None and snapshot.text == "zażółć 🌍"
        assert not snapshot.sensitive
        await clipboard.write_text("tekst")

    asyncio.run(scenario())
    assert calls == [
        (("wl-types",), None),
        (("wl-paste",), None),
        (("wl-copy",), b"tekst"),
    ]


def test_sensitive_mime_marker_skips_text_read() -> None:
    calls: list[tuple[str, ...]] = []

    async def runner(command, _input_bytes):
        calls.append(tuple(command))
        return 0, b"x-kde-passwordManagerHint\ntext/plain", b""

    clipboard = CommandClipboard(
        read_command=["wl-paste"],
        write_command=["wl-copy"],
        types_command=["wl-paste", "--list-types"],
        command_runner=runner,
    )
    snapshot = asyncio.run(clipboard.read_text())
    assert snapshot is not None and snapshot.sensitive
    assert calls == [("wl-paste", "--list-types")]


def test_no_available_provider_has_clear_error() -> None:
    with pytest.raises(ClipboardUnavailableError, match="no configured clipboard provider"):
        resolve_linux_clipboard([], env={"WAYLAND_DISPLAY": "wayland-0"})


def test_application_can_inject_a_custom_provider() -> None:
    class CustomClipboard:
        async def read_text(self):
            return None

        async def write_text(self, _text):
            return None

    custom = CustomClipboard()

    class CustomProvider:
        def create(self, _env):
            return custom

    assert (
        resolve_linux_clipboard([CustomProvider()], env={"WAYLAND_DISPLAY": "wayland-0"})
        is custom
    )
