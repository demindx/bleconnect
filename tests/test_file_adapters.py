import asyncio

import pytest

from bleconnect.adapters.filesystem.file_sink import (
    LocalFileSinkFactory,
    sanitize_file_name,
)
from bleconnect.adapters.filesystem.file_source import LocalFileSource


def test_local_file_source_reads_chunks(tmp_path) -> None:
    path = tmp_path / "hello.txt"
    path.write_bytes(b"hello world")

    async def scenario() -> None:
        source = LocalFileSource(path)
        assert source.name == "hello.txt"
        assert source.size == 11
        chunks = [chunk async for chunk in source.read_chunks(4)]
        assert chunks == [b"hell", b"o wo", b"rld"]

    asyncio.run(scenario())


def test_local_file_sink_finishes_file(tmp_path) -> None:
    async def scenario() -> None:
        factory = LocalFileSinkFactory(tmp_path)
        sink = await factory.create("hello.txt", 5)
        await sink.write(b"hello")
        await sink.finish("unused")
        assert (tmp_path / "hello.txt").read_bytes() == b"hello"
        assert not (tmp_path / "hello.txt.part").exists()

    asyncio.run(scenario())


def test_local_file_sink_avoids_name_collisions(tmp_path) -> None:
    (tmp_path / "hello.txt").write_bytes(b"old")

    async def scenario() -> None:
        factory = LocalFileSinkFactory(tmp_path)
        sink = await factory.create("hello.txt", 3)
        await sink.write(b"new")
        await sink.finish("unused")
        assert (tmp_path / "hello (1).txt").read_bytes() == b"new"

    asyncio.run(scenario())


def test_local_file_sink_abort_removes_partial_file(tmp_path) -> None:
    async def scenario() -> None:
        factory = LocalFileSinkFactory(tmp_path)
        sink = await factory.create("hello.txt", 5)
        await sink.write(b"hel")
        await sink.abort()
        assert not (tmp_path / "hello.txt").exists()
        assert not (tmp_path / "hello.txt.part").exists()

    asyncio.run(scenario())


def test_local_file_sink_rejects_wrong_size(tmp_path) -> None:
    async def scenario() -> None:
        factory = LocalFileSinkFactory(tmp_path)
        sink = await factory.create("hello.txt", 5)
        await sink.write(b"hi")
        with pytest.raises(OSError):
            await sink.finish("unused")
        assert not (tmp_path / "hello.txt").exists()

    asyncio.run(scenario())


def test_sanitize_file_name_removes_paths_and_hidden_prefixes() -> None:
    assert sanitize_file_name("../../etc/passwd") == "passwd"
    assert sanitize_file_name("..\\..\\secret.txt") == "secret.txt"
    assert sanitize_file_name(".hidden") == "hidden"
    with pytest.raises(ValueError):
        sanitize_file_name("..")
