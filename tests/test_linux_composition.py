import asyncio

from bleconnect.adapters.linux.clipboard import PollingClipboardWatcher
from bleconnect.application.ports import ClipboardSnapshot
from bleconnect.platform.linux import (
    build_linux_clipboard_watcher,
    build_linux_file_sink_factory,
    build_linux_pairing_service,
    build_linux_trusted_devices,
)


class MemoryClipboard:
    async def read_text(self):
        return ClipboardSnapshot("text")

    async def write_text(self, text: str) -> None:
        pass


def test_linux_helpers_build_adapters(tmp_path) -> None:
    async def scenario() -> None:
        watcher = build_linux_clipboard_watcher(MemoryClipboard(), {})
        assert isinstance(watcher, PollingClipboardWatcher)

        repository = build_linux_trusted_devices(tmp_path / "trusted.json")
        assert await repository.list_trusted() == []

        sink_factory = build_linux_file_sink_factory(tmp_path / "downloads")
        sink = await sink_factory.create("hello.txt", 5)
        await sink.write(b"hello")
        await sink.finish("unused")
        assert (tmp_path / "downloads" / "hello.txt").read_bytes() == b"hello"

        pairing = build_linux_pairing_service(repository)
        assert pairing is not None

    asyncio.run(scenario())
