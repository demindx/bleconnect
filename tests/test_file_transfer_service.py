import asyncio
import hashlib

import pytest

from bleconnect.application.file_transfer_service import (
    FileTransferService,
    TransferError,
    TransferState,
)
from tests.support import (
    MemoryFileSource,
    MemorySinkFactory,
    MutatingLink,
    QueueLink,
    paired_links,
)


async def _pump(
    link: QueueLink, service: FileTransferService, stop: asyncio.Event
) -> None:
    try:
        while not stop.is_set():
            packet = await link.receive()
            await service.handle_packet(packet)
    except asyncio.CancelledError:
        pass


async def _run_transfer(
    sender: FileTransferService,
    receiver: FileTransferService,
    sender_link: QueueLink,
    receiver_link: QueueLink,
    source: MemoryFileSource,
):
    stop = asyncio.Event()
    tasks = [
        asyncio.create_task(_pump(sender_link, sender, stop)),
        asyncio.create_task(_pump(receiver_link, receiver, stop)),
    ]
    try:
        return await asyncio.wait_for(sender.send(source), timeout=5)
    finally:
        stop.set()
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


def test_send_and_receive_file() -> None:
    async def scenario() -> None:
        sender_link, receiver_link = paired_links()
        sender_factory = MemorySinkFactory()
        receiver_factory = MemorySinkFactory()
        sender = FileTransferService(
            sender_link, sender_factory, chunk_size=1024
        )
        receiver = FileTransferService(
            receiver_link, receiver_factory, chunk_size=1024
        )
        source = MemoryFileSource("hello.txt", b"hello world" * 1000)

        progress = await _run_transfer(
            sender, receiver, sender_link, receiver_link, source
        )

        assert progress.state is TransferState.COMPLETED
        assert sender.state is TransferState.COMPLETED
        assert receiver.state is TransferState.COMPLETED
        assert len(receiver_factory.sinks) == 1
        sink = receiver_factory.sinks[0]
        assert bytes(sink.data) == source.data
        assert sink.finished is True
        assert sink.sha256 == hashlib.sha256(source.data).hexdigest()

    asyncio.run(scenario())


def test_empty_file_transfers() -> None:
    async def scenario() -> None:
        sender_link, receiver_link = paired_links()
        sender = FileTransferService(sender_link, MemorySinkFactory())
        receiver = FileTransferService(receiver_link, MemorySinkFactory())
        source = MemoryFileSource("empty.bin", b"")

        progress = await _run_transfer(
            sender, receiver, sender_link, receiver_link, source
        )

        assert progress.state is TransferState.COMPLETED
        assert receiver.state is TransferState.COMPLETED

    asyncio.run(scenario())


def test_receiver_rejects_file_over_limit() -> None:
    async def scenario() -> None:
        sender_link, receiver_link = paired_links()
        sender = FileTransferService(
            sender_link, MemorySinkFactory(), max_bytes=10_000
        )
        receiver_factory = MemorySinkFactory()
        receiver = FileTransferService(
            receiver_link, receiver_factory, max_bytes=100
        )
        source = MemoryFileSource("large.bin", b"x" * 500)

        with pytest.raises(TransferError) as error:
            await _run_transfer(
                sender, receiver, sender_link, receiver_link, source
            )

        assert error.value.code == "file_too_large"
        assert receiver_factory.sinks == []

    asyncio.run(scenario())


def test_sender_rejects_file_over_limit_before_sending() -> None:
    async def scenario() -> None:
        sender_link, _ = paired_links()
        sender = FileTransferService(
            sender_link, MemorySinkFactory(), max_bytes=10
        )
        source = MemoryFileSource("large.bin", b"x" * 20)

        with pytest.raises(TransferError) as error:
            await sender.send(source)

        assert error.value.code == "file_too_large"

    asyncio.run(scenario())


def test_hash_mismatch_aborts_received_file() -> None:
    async def scenario() -> None:
        sender_link, receiver_link = paired_links()
        sender = FileTransferService(
            MutatingLink(sender_link, "0" * 64), MemorySinkFactory()
        )
        receiver_factory = MemorySinkFactory()
        receiver = FileTransferService(receiver_link, receiver_factory)
        source = MemoryFileSource("bad.bin", b"payload")

        with pytest.raises(TransferError) as error:
            await _run_transfer(
                sender, receiver, sender_link, receiver_link, source
            )

        assert error.value.code == "hash_mismatch"
        sink = receiver_factory.sinks[0]
        assert sink.aborted is True
        assert sink.finished is False
        assert bytes(sink.data) == b""

    asyncio.run(scenario())
